"""Rank reviewable candidates, preserving the existing mapper as the baseline."""
from rapidfuzz.fuzz import ratio
from contracts.interfaces.ingestion import ColumnSuggestion, MappingCandidate, MappingReply, MappingSheetReply
from app.ingest.mapping import ENTITY_FIELDS, map_sheet, norm_header
from app.ingest.parsing import FileError, ParsedFile
from app.ingest.profiling import ScopedMaster, profile

LEXICAL_CUTOFF = 0.60  # Candidate retrieval only. Never a probability or acceptance threshold.
QUANTITIES = {'demand_qty', 'on_hand_qty', 'available_qty', 'allocated_qty', 'qty_per', 'base_qty', 'safety_stock_qty', 'scrap_rate'}

# Server-owned vocabulary only. Never cache uploaded headers/values across requests.
VOCABULARY = {entity: {field: {
    'standard': norm_header(field),
    'strong': frozenset(map(norm_header, spec['strong'])),
    'weak': frozenset(map(norm_header, spec['weak'])),
    'all': tuple(dict.fromkeys(map(norm_header, [field] + spec['strong'] + spec['weak']))),
} for field, spec in fields.items()} for entity, fields in ENTITY_FIELDS.items()}


def lexical_similarity(labels, aliases):
    """Full-string normalized Indel similarity; 0..1 ranking aid, never a probability."""
    return max((ratio(label, alias, processor=None) / 100 for label in labels for alias in aliases), default=0.0)


def compatible(field, header, column):
    # Matching may ignore annotations such as '(EA)', but semantic guards must
    # still see qualifiers such as '(반품)' or '(출고일자 기준)'. Keep the mapper unchanged.
    label = norm_header(header.translate(str.maketrans({char: ' ' for char in '()（）[]'})))
    if field == 'product_id' and any(word in label for word in ('자재', 'material')):
        return False, 'MATERIAL_IS_NOT_PRODUCT'
    if field == 'material_id' and any(word in label for word in ('제품', '상품', 'product')):
        return False, 'PRODUCT_IS_NOT_MATERIAL'
    if field in QUANTITIES:
        if any(word in label for word in ('금액', '단가', 'amount', 'price', 'cost')):
            return False, 'MONEY_IS_NOT_QUANTITY'
        if field == 'demand_qty' and any(word in label for word in ('반품', '취소', 'return', 'cancel', '생산', '한도', 'capacity', '시간', '인시')):
            return False, 'OTHER_BUSINESS_MEASURE_IS_NOT_DEMAND'
        if column.total_rows > column.empty_count and column.format_match_rates['DECIMAL'] != 1:
            return False, 'NON_DECIMAL_VALUES'
    if field == 'period' and any(word in label for word in ('출고', 'ship')):
        return False, 'SHIPPING_IS_NOT_CONFIRMED_DEMAND_DATE'
    if field == 'on_hand_qty' and any(word in label for word in ('가용', 'available')):
        return False, 'AVAILABLE_IS_NOT_ON_HAND'
    if field == 'available_qty' and any(word in label for word in ('현재고', 'onhand')):
        return False, 'ON_HAND_IS_NOT_AVAILABLE'
    if field == 'product_id' and column.known_product_match_ratio == 0 and (column.known_material_match_ratio or 0) > 0:
        return False, 'ONLY_MATERIAL_MASTER_MATCHES'
    if field == 'material_id' and column.known_material_match_ratio == 0 and (column.known_product_match_ratio or 0) > 0:
        return False, 'ONLY_PRODUCT_MASTER_MATCHES'
    return True, ''


def recommend(parsed: ParsedFile, entity: str, dataset_id: str, master: ScopedMaster | None = None, overrides=None):
    if entity not in ENTITY_FIELDS:
        raise FileError('UNSUPPORTED_ENTITY', 'Profiling mapping supports product/material/monthly_demand/BOM/inventory only.')
    if set(overrides or {}) - set(ENTITY_FIELDS[entity]):
        raise FileError('BAD_COLUMN_OVERRIDES', 'Unknown target in column overrides.')
    analysis = profile(parsed, dataset_id, master)
    result = []
    for sheet, stats in zip(parsed.sheets, analysis.sheets):
        baseline = map_sheet(sheet, overrides, entity)
        holds = [hold.code + ':' + (hold.field or '') for hold in baseline.holds]
        suggestions = []
        for header, column in zip(sheet.header, stats.columns):
            ranked, rejected = [], []
            contradicted_selection = False
            labels = {norm_header(label) for label in header.labels}
            for field, spec in ENTITY_FIELDS[entity].items():
                mapped = baseline.fields.get(field)
                vocabulary = VOCABULARY[entity][field]
                exact = vocabulary['standard'] in labels
                strong = bool(vocabulary['strong'] & labels)
                weak = bool(vocabulary['weak'] & labels)
                lexical = lexical_similarity(labels, vocabulary['all'])
                master_rate = column.known_product_match_ratio if field == 'product_id' else column.known_material_match_ratio if field == 'material_id' else None
                by_profile = master_rate is not None and master_rate >= 0.8
                selected = mapped is not None and mapped.col == header.col
                if not (selected or exact or strong or weak or lexical >= LEXICAL_CUTOFF or by_profile):
                    continue
                allowed, reason = compatible(field, header.display, column)
                if not allowed:
                    rejected.append(field + ':' + reason)
                    if selected:
                        holds.append('PROFILE_CONTRADICTION:' + field)
                        contradicted_selection = True
                    continue
                if selected and mapped.method == 'USER_OVERRIDE':
                    method, rank = 'USER_OVERRIDE', 0
                elif exact:
                    method, rank = 'STANDARD_EXACT', 1
                elif strong:
                    method, rank = 'ALIAS_STRONG', 2
                elif weak:
                    method, rank = 'ALIAS_WEAK', 3
                elif by_profile:
                    method, rank = 'HEADER_AND_VALUE_PROFILE', 4
                else:
                    method, rank = 'LEXICAL_SIMILARITY', 5
                evidence = [method, 'FORMAT_COUNTS_MEASURED; SEMANTICS_NOT_PROVEN']
                if method == 'LEXICAL_SIMILARITY':
                    evidence.append(f'RAPIDFUZZ_RATIO={lexical:.6f}; RANKING_ONLY_NOT_CONFIDENCE')
                if by_profile:
                    evidence.append(f'APPROVED_MASTER_MATCH_RATIO={master_rate:.6f}')
                if field in QUANTITIES:
                    evidence.append(f'DECIMAL_MATCH_RATIO={column.format_match_rates["DECIMAL"]:.6f}')
                ranked.append((rank, -lexical, field, MappingCandidate(target_field=field, method=method, evidence=evidence)))
            if contradicted_selection:
                # A rejected known role must not turn into another role through fuzzy fallback.
                ranked = []
                rejected.append('SOURCE_ROLE_CONTRADICTION_REQUIRES_REVIEW')
            candidates = [item[3] for item in sorted(ranked, key=lambda item: item[:3])[:3]]
            suggestions.append(ColumnSuggestion(col=header.col, source_column=header.display[:200], suggestions=candidates,
                                                 unresolved_reasons=sorted(set(rejected))[:12]))
        for field, spec in ENTITY_FIELDS[entity].items():
            mapped = baseline.fields.get(field)
            if spec['required'] and (mapped is None or mapped.review_required):
                holds.append('USER_SELECTION_REQUIRED:' + field)
        status = 'HOLD' if holds else baseline.status
        result.append(MappingSheetReply(sheet=sheet.name, status=status, existing_mapping={name: item.col for name, item in baseline.fields.items()},
                                       suggestions=suggestions, holds=sorted(set(holds))))
    return MappingReply(dataset_id=dataset_id, entity=entity, source_sha256=parsed.sha256,
                        master_scope=master.dataset_id if master else None, master_digest=analysis.master_digest, sheets=result)
