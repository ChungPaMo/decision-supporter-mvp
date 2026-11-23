import { BatchDetail, BatchSummary, Entity, Page, ValidationResult } from '../types/api';
import { ForecastExecution, ForecastExecutionSummary, ForecastRunParameters, ForecastRunReply } from '../types/engine';
import { ClassificationResult, DatasetDetail, PlanCandidate, PlanDecisionEvent, PlanDecisionRequest, PlanExecutionCommand, PlanExecutionDetail, PlanExecutionReply, PlanExecutionSummary, PlanningReply } from '../types/modules';
import { useProductionStore } from '../store/productionStore';
import { ClassifiedMappingReply, MappingReply, ProfileReply, SalesTransformPolicy, TransformationDetail, TransformationSummary, TransformReply } from '../types/ingestion';

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

// 데이터셋 DB를 조회하지 않는 경로. 그 외 모든 요청에는 dataset_id 를 붙인다.
// /ingest/* 는 데이터셋 범위 요청이다(이력은 영구 API). 무저장 분류(/classifications/file)만 범위 밖이다.
const UNSCOPED = ['/health', '/datasets', '/classifications/', '/exports/plans/xlsx', '/dev/'];
const STALE = { detail: { code: 'DATASET_CHANGED', message: '데이터셋이 변경되어 이전 요청 결과를 버렸습니다.' } };
const currentDataset = () => useProductionStore.getState().datasetId;

class ApiClient {
  private scoped(path: string, datasetId: string) {
    if (UNSCOPED.some((prefix) => path.startsWith(prefix))) return path;
    return `${path}${path.includes('?') ? '&' : '?'}dataset_id=${encodeURIComponent(datasetId)}`;
  }

  // ── 데이터 입력 보조 (저장하지 않음). 분류·후보·미리보기 성공은 등록·승인 성공이 아니다. ──
  private assistForm(file: File, useApprovedMaster: boolean) {
    const form = new FormData();
    form.append('file', file);
    form.append('use_approved_master', String(useApprovedMaster));
    return form;
  }

  async profileFile(file: File, useApprovedMaster: boolean): Promise<ProfileReply> {
    const form = this.assistForm(file, useApprovedMaster);
    form.append('include_samples', 'false');
    return this.request('POST', '/ingest/profile', { formData: form });
  }

  async classifiedMapping(file: File, entity: Entity | null, overrides: Record<string, string>, useApprovedMaster: boolean): Promise<ClassifiedMappingReply> {
    const form = this.assistForm(file, useApprovedMaster);
    if (entity) form.append('entity', entity);
    form.append('column_overrides', JSON.stringify(overrides));
    form.append('sample_row_limit', '0');
    return this.request('POST', '/ingest/classified-mapping', { formData: form });
  }

  async mappingSuggestions(file: File, entity: Entity, overrides: Record<string, string>, useApprovedMaster: boolean): Promise<MappingReply> {
    const form = this.assistForm(file, useApprovedMaster);
    form.append('entity', entity);
    form.append('column_overrides', JSON.stringify(overrides));
    return this.request('POST', '/ingest/mapping-suggestions', { formData: form });
  }

  private transformForm(files: File[], policy: SalesTransformPolicy, useApprovedMaster: boolean) {
    const form = new FormData();
    // 파일 순서가 지문에 포함되므로 미리보기와 저장에서 같은 순서를 유지한다.
    files.forEach((file) => form.append('files', file));
    form.append('policy', JSON.stringify(policy));
    form.append('use_approved_master', String(useApprovedMaster));
    return form;
  }

  async transformPreview(files: File[], policy: SalesTransformPolicy, useApprovedMaster: boolean): Promise<TransformReply> {
    return this.request('POST', '/ingest/transform-preview?offset=0&limit=500', { formData: this.transformForm(files, policy, useApprovedMaster) });
  }

  // 변환 이력 저장 + 승인 전 배치 생성. 201 신규 / 200 재사용. 승인은 별도의 배치 승인으로만 일어난다.
  async createTransformation(files: File[], policy: SalesTransformPolicy, useApprovedMaster: boolean,
    expectedResultDigest: string, createdBy: string, sourceNote: string): Promise<{ detail: TransformationDetail; reused: boolean }> {
    const form = this.transformForm(files, policy, useApprovedMaster);
    form.append('expected_result_digest', expectedResultDigest);
    form.append('created_by', createdBy);
    form.append('source_note', sourceNote);
    let status = 201;
    const detail = await this.request<TransformationDetail>('POST', '/ingest/transformations', { formData: form, onStatus: (code) => { status = code; } });
    return { detail, reused: status === 200 };
  }

  async transformations(limit = 50, offset = 0): Promise<Page<TransformationSummary>> {
    return this.request('GET', `/ingest/transformations?limit=${limit}&offset=${offset}`);
  }

  async getTransformation(transformationId: string): Promise<TransformationDetail> {
    return this.request('GET', `/ingest/transformations/${encodeURIComponent(transformationId)}?offset=0&limit=500`);
  }

  async listDatasets(): Promise<DatasetDetail[]> {
    return this.request('GET', '/datasets');
  }

  // 저장되는 계획 실행. 엔진 미연결 동안 생성은 501 MODULE_NOT_IMPLEMENTED 가 정상 응답이다.
  async createPlanExecution(command: PlanExecutionCommand): Promise<PlanExecutionReply> {
    return this.request('POST', '/plan-executions', { body: command });
  }

  async planExecutions(limit = 20, offset = 0): Promise<Page<PlanExecutionSummary>> {
    return this.request('GET', `/plan-executions?limit=${limit}&offset=${offset}`);
  }

  async getPlanExecution(executionId: string): Promise<PlanExecutionDetail> {
    return this.request('GET', `/plan-executions/${encodeURIComponent(executionId)}`);
  }

  async planCandidates(executionId: string): Promise<PlanCandidate[]> {
    return this.request('GET', `/plan-executions/${encodeURIComponent(executionId)}/candidates`);
  }

  async planDecisions(executionId: string): Promise<{ items: PlanDecisionEvent[] }> {
    return this.request('GET', `/plan-executions/${encodeURIComponent(executionId)}/decisions`);
  }

  // REVIEW/REJECT 만 기록된다. APPROVE 는 인증·정책 미구현으로 501 PLAN_APPROVAL_DISABLED.
  async decidePlan(executionId: string, body: PlanDecisionRequest): Promise<PlanExecutionDetail> {
    return this.request('POST', `/plan-executions/${encodeURIComponent(executionId)}/decisions`, { body });
  }

  private async request<T>(
    method: string,
    path: string,
    options?: {
      headers?: Record<string, string>;
      body?: any;
      formData?: FormData;
      onStatus?: (status: number) => void;
    }
  ): Promise<T> {
    // 요청 시점의 데이터셋을 고정한다. 응답 전에 데이터셋이 바뀌면 결과를 화면에 넘기지 않는다.
    const datasetId = currentDataset();
    const url = `${API_BASE}${this.scoped(path, datasetId)}`;
    // 데이터셋과 무관한 요청(/datasets, /health 등)은 데이터셋이 바뀌어도 결과를 버리지 않는다.
    const stale = () => url.includes('dataset_id=') && currentDataset() !== datasetId;
    const config: RequestInit = { method };

    if (options?.formData) {
      config.body = options.formData;
    } else if (options?.body) {
      config.headers = { 'Content-Type': 'application/json', ...options.headers };
      config.body = JSON.stringify(options.body);
    } else {
      config.headers = options?.headers;
    }

    let res: Response;
    try {
      res = await fetch(url, config);
    } catch {
      throw { detail: { code: 'NETWORK_ERROR', message: '서버에 연결할 수 없습니다. 연결과 CORS 설정을 확인한 뒤 다시 조회하세요.' } };
    }
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: { code: 'NETWORK_ERROR', message: res.statusText } }));
      throw stale() ? STALE : error;
    }
    const payload = await res.json();
    if (stale()) throw STALE;
    options?.onStatus?.(res.status);
    return payload;
  }

  // 건강 체크
  async classifyFile(file: File, includeSamples: boolean): Promise<ClassificationResult> {
    const formData = new FormData();
    formData.append('file', file); formData.append('sample_row_limit', includeSamples ? '5' : '0');
    return this.request('POST', '/classifications/file', { formData });
  }

  async requestPlan(executionId: string, productIds?: string[], targetMonth?: string): Promise<PlanningReply> {
    const execution = await this.getForecast(executionId);
    const rows = execution.result?.forecasts ?? [];
    if (!rows.length) throw new Error('계획에 사용할 실제 예측 결과가 없습니다.');
    return this.request('POST', '/plans', { body: {
      forecast_execution_id: executionId, product_ids: productIds ?? [...new Set(rows.map(row => row.product_id))],
      target_month: targetMonth ?? rows[0].target_month, as_of_date: execution.parameters.trained_until,
    } });
  }

  async runForecast(parameters: ForecastRunParameters): Promise<ForecastRunReply> {
    return this.request('POST', '/forecasts', { body: parameters });
  }

  async forecastHistory(limit = 20, offset = 0): Promise<Page<ForecastExecutionSummary>> {
    return this.request('GET', `/forecasts?limit=${limit}&offset=${offset}`);
  }

  async getForecast(executionId: string): Promise<ForecastExecution> {
    return this.request('GET', `/forecasts/${encodeURIComponent(executionId)}`);
  }

  async health() {
    return this.request('GET', '/health');
  }

  // 저장 없는 검증. /batches 가 501 인 동안 실제 서버에 붙는 유일한 업로드 경로
  async previewBatch(file: File, entity: Entity): Promise<ValidationResult> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('entity', entity);
    return this.request('POST', '/ingest/preview', { formData });
  }

  // 파일 업로드 (검증)
  async uploadBatch(
    file: File,
    entity: Entity = 'monthly_demand',
    options?: {
      default_unit?: string;
      column_overrides?: Record<string, string>;
      sheet?: string;
      source_type?: string;
      source_note?: string;
      created_by?: string;
    }
  ): Promise<BatchDetail> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('entity', entity);
    if (options?.default_unit) formData.append('default_unit', options.default_unit);
    if (options?.column_overrides) formData.append('column_overrides', JSON.stringify(options.column_overrides));
    if (options?.sheet) formData.append('sheet', options.sheet);
    if (options?.source_type) formData.append('source_type', options.source_type);
    if (options?.source_note) formData.append('source_note', options.source_note);
    if (options?.created_by) formData.append('created_by', options.created_by);

    return this.request('POST', '/batches', { formData });
  }

  // 배치 목록
  async listBatches(status?: string, limit = 20, offset = 0) {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return this.request<Page<BatchSummary>>('GET', `/batches?${params}`);
  }

  async allBatches(): Promise<BatchSummary[]> {
    const rows: BatchSummary[] = [];
    let offset = 0;
    while (true) {
      const page = await this.listBatches(undefined, 100, offset);
      rows.push(...page.items);
      offset += page.items.length;
      if (offset >= page.total) return rows;
      if (page.items.length === 0) throw new Error('배치 목록을 끝까지 읽지 못했습니다. 다시 조회하세요.');
    }
  }

  async approvedData(entity: Entity): Promise<Array<Record<string, unknown>>> {
    const paths: Record<Entity, string> = { product: '/products', material: '/materials', bom: '/boms', inventory: '/inventory', monthly_demand: '/demand/monthly', capacity: '/capacity', routing: '/routings' };
    const page = await this.request<Page<Record<string, unknown>>>('GET', `${paths[entity]}?limit=100&offset=0`);
    if (entity === 'bom') return page.items.flatMap((row) => (row.lines as Array<Record<string, unknown>>).map((line) => ({ ...row, lines: undefined, ...line })));
    // CAPA·Routing 은 section/payload 구조다. 수량·설비시간·인시를 합치거나 환산하지 않고 원래 값 그대로 편다.
    if (entity === 'capacity' || entity === 'routing') return page.items.map((row) => ({ section: row.section, ...(row.payload as Record<string, unknown>), batch_id: row.batch_id }));
    return page.items;
  }

  // 배치 상세
  async getBatch(batchId: string): Promise<BatchDetail> {
    return this.request('GET', `/batches/${batchId}`);
  }

  // 재검증
  async revalidateBatch(
    batchId: string,
    data: {
      expected_version: number;
      column_overrides?: Record<string, string>;
      default_unit?: string | null;
      sheet?: string | null;
    }
  ): Promise<BatchDetail> {
    return this.request('POST', `/batches/${batchId}/revalidate`, { body: data });
  }

  // 승인
  async approveBatch(batchId: string, approved_by: string, expected_result_digest: string): Promise<BatchDetail> {
    return this.request('POST', `/batches/${batchId}/approve`, {
      body: { approved_by, expected_result_digest },
    });
  }

  // 반려
  async rejectBatch(batchId: string, rejected_by: string, reason: string): Promise<BatchDetail> {
    return this.request('POST', `/batches/${batchId}/reject`, {
      body: { rejected_by, reason },
    });
  }

  // 제품 조회
  async listProducts(q?: string, limit = 20, offset = 0) {
    const params = new URLSearchParams();
    if (q) params.append('q', q);
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return this.request('GET', `/products?${params}`);
  }

  // 자재 조회
  async listMaterials(q?: string, limit = 20, offset = 0) {
    const params = new URLSearchParams();
    if (q) params.append('q', q);
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return this.request('GET', `/materials?${params}`);
  }

  // BOM 조회
  async listBOMs(productId?: string, activeOnly = true, limit = 20, offset = 0) {
    const params = new URLSearchParams();
    if (productId) params.append('product_id', productId);
    params.append('active_only', String(activeOnly));
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return this.request('GET', `/boms?${params}`);
  }

  // 재고 조회
  async listInventory(itemType?: string, itemId?: string, limit = 20, offset = 0) {
    const params = new URLSearchParams();
    if (itemType) params.append('item_type', itemType);
    if (itemId) params.append('item_id', itemId);
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return this.request('GET', `/inventory?${params}`);
  }

  // 월별 수요 조회
  async listDemand(productId?: string, limit = 20, offset = 0) {
    const params = new URLSearchParams();
    if (productId) params.append('product_id', productId);
    params.append('limit', String(limit));
    params.append('offset', String(offset));
    return this.request('GET', `/demand/monthly?${params}`);
  }

  // Excel 다운로드
  async downloadPlanXlsx(planJson: unknown): Promise<string> {
    const res = await fetch(`${API_BASE}/exports/plans/xlsx`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(planJson),
    });

    if (!res.ok) {
      const error = await res.json();
      throw error;
    }

    const header = res.headers.get('Content-Disposition') ?? '';
    const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/);
    const asciiMatch = header.match(/filename="([^"]+)"/);
    const filename = utf8Match ? decodeURIComponent(utf8Match[1]) : asciiMatch?.[1] ?? 'DEMO_UNVERIFIED_plan_export.xlsx';

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
    return filename;
  }
}

export const apiClient = new ApiClient();
