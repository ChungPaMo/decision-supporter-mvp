"""Immutable plan executions and append-only decisions; no source data changes."""
from alembic import op
from sqlalchemy import text

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE plan_execution (
 execution_id uuid PRIMARY KEY, forecast_execution_id uuid NOT NULL REFERENCES forecast_run,
 base_plan_execution_id uuid, scenario_type text NOT NULL CHECK(scenario_type IN ('BASE','WHAT_IF')),
 target_month char(7) NOT NULL CHECK(target_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'), as_of_date date NOT NULL,
 status text NOT NULL CHECK(status IN ('COMPLETED','PARTIAL','FAILED')),
 input_digest text NOT NULL CHECK(input_digest ~ '^sha256:[0-9a-f]{64}$'),
 result_digest text NOT NULL CHECK(result_digest ~ '^sha256:[0-9a-f]{64}$'), dedup_key char(64) NOT NULL,
 input_snapshot jsonb NOT NULL, result_snapshot jsonb NOT NULL,
 engine_version varchar(80) NOT NULL, policy_version text, runtime_identity jsonb NOT NULL,
 data_origin text NOT NULL CHECK(data_origin IN ('REAL_ENGINE','TEST_DOUBLE')),
 created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz NOT NULL DEFAULT clock_timestamp(), error_code text,
 created_txid bigint NOT NULL DEFAULT txid_current(),
 UNIQUE(execution_id,forecast_execution_id,data_origin),
 FOREIGN KEY(base_plan_execution_id,forecast_execution_id,data_origin) REFERENCES plan_execution(execution_id,forecast_execution_id,data_origin),
 CHECK((scenario_type='BASE' AND base_plan_execution_id IS NULL) OR (scenario_type='WHAT_IF' AND base_plan_execution_id IS NOT NULL)),
 CHECK((status='COMPLETED' AND result_snapshot->>'status'='OK') OR
       (status='PARTIAL' AND result_snapshot->>'status'='PARTIAL') OR
       (status='FAILED' AND result_snapshot->>'status' IN ('FAILED','UNSUPPORTED','INPUT_INVALID')))
);
CREATE UNIQUE INDEX uq_plan_dedup ON plan_execution(dedup_key,data_origin) WHERE status<>'FAILED';
CREATE TABLE plan_candidate (
 execution_id uuid NOT NULL REFERENCES plan_execution, plan_id varchar(40) NOT NULL,
 plan_type text NOT NULL CHECK(plan_type IN ('BASELINE','STABLE','COST_SAVING','CUSTOM')),
 label text NOT NULL, feasibility text NOT NULL CHECK(feasibility IN ('FEASIBLE','UNVERIFIED','INFEASIBLE')),
 production_rows jsonb NOT NULL, policy_ref text, unverified jsonb NOT NULL, payload jsonb NOT NULL,
 PRIMARY KEY(execution_id,plan_id)
);
CREATE TABLE plan_constraint_evaluation (
 execution_id uuid, plan_id varchar(40), constraint_id varchar(40),
 dimension text NOT NULL CHECK(dimension IN ('QUANTITY','WORK_HOURS','EQUIPMENT_HOURS','MATERIAL','SAFETY_STOCK','OTHER')),
 period char(7) NOT NULL, resource_id varchar(40), product_id varchar(40), step_id varchar(40),
 status text NOT NULL CHECK(status IN ('SATISFIED','VIOLATED','UNVERIFIED')),
 limit_value numeric(20,6) CHECK(limit_value>=0), used_value numeric(20,6) CHECK(used_value>=0), unit varchar(40),
 time_basis text CHECK(time_basis IN ('ELAPSED','PERSON_HOUR','MACHINE_HOUR')),
 strength text CHECK(strength IN ('HARD','SOFT')), application_state text NOT NULL CHECK(application_state IN ('APPLIED','MISSING_INPUT','UNSUPPORTED')),
 input_refs jsonb NOT NULL, reason_codes jsonb NOT NULL, payload jsonb NOT NULL,
 PRIMARY KEY(execution_id,plan_id,constraint_id), FOREIGN KEY(execution_id,plan_id) REFERENCES plan_candidate
);
CREATE TABLE plan_material_requirement (
 execution_id uuid, plan_id varchar(40), material_id varchar(40), period char(7),
 required_qty numeric(20,6) CHECK(required_qty>=0), available_qty numeric(20,6) CHECK(available_qty>=0), shortage_qty numeric(20,6) CHECK(shortage_qty>=0),
 unit varchar(40) NOT NULL, input_refs jsonb NOT NULL, payload jsonb NOT NULL,
 PRIMARY KEY(execution_id,plan_id,material_id,period), FOREIGN KEY(execution_id,plan_id) REFERENCES plan_candidate
);
CREATE TABLE plan_execution_input (
 execution_id uuid REFERENCES plan_execution, batch_id uuid REFERENCES import_batch, batch_version integer NOT NULL,
 source_sha256 char(64) NOT NULL, result_digest char(64), approved_at timestamptz NOT NULL,
 PRIMARY KEY(execution_id,batch_id)
);
CREATE TABLE plan_review (
 execution_id uuid PRIMARY KEY REFERENCES plan_execution, selected_plan_id varchar(40),
 status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','REVIEW','APPROVED','REJECTED')),
 version integer NOT NULL DEFAULT 1 CHECK(version>=1),
 FOREIGN KEY(execution_id,selected_plan_id) REFERENCES plan_candidate
);
CREATE TABLE plan_decision (
 decision_id uuid PRIMARY KEY, execution_id uuid NOT NULL, plan_id varchar(40) NOT NULL,
 action text NOT NULL CHECK(action IN ('REVIEW','APPROVE','REJECT')),
 status_before text NOT NULL, status_after text NOT NULL, review_version integer NOT NULL,
 actor_id varchar(60) NOT NULL, auth_verified boolean NOT NULL DEFAULT false, reason text NOT NULL CHECK(length(reason)>0),
 input_digest text NOT NULL, decided_at timestamptz NOT NULL DEFAULT now(), exception_codes jsonb NOT NULL DEFAULT '[]',
 UNIQUE(execution_id,review_version), FOREIGN KEY(execution_id,plan_id) REFERENCES plan_candidate
);
CREATE FUNCTION guard_plan_child() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM plan_execution WHERE execution_id=NEW.execution_id AND created_txid=txid_current()) THEN
  RAISE EXCEPTION 'plan rows must be saved atomically with execution' USING ERRCODE='check_violation';
 END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION verify_plan_rows() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (SELECT count(*) FROM plan_candidate WHERE execution_id=NEW.execution_id) <> jsonb_array_length(NEW.result_snapshot->'plans') OR
    (SELECT count(*) FROM plan_constraint_evaluation WHERE execution_id=NEW.execution_id) <> jsonb_array_length(NEW.result_snapshot->'constraint_evaluations') OR
    (SELECT count(*) FROM plan_material_requirement WHERE execution_id=NEW.execution_id) <> jsonb_array_length(NEW.result_snapshot->'material_requirements') OR
    (SELECT count(*) FROM plan_execution_input WHERE execution_id=NEW.execution_id) <> jsonb_array_length(NEW.input_snapshot->'approved_inputs'->'sources') OR
    NOT EXISTS(SELECT 1 FROM plan_review WHERE execution_id=NEW.execution_id) THEN
  RAISE EXCEPTION 'incomplete plan execution' USING ERRCODE='check_violation';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER trg_plan_count AFTER INSERT ON plan_execution DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION verify_plan_rows();
CREATE FUNCTION check_plan_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM import_batch WHERE batch_id=NEW.batch_id AND status='APPROVED' AND blocking_error_count=0
  AND version=NEW.batch_version AND source_sha256=NEW.source_sha256 AND result_digest IS NOT DISTINCT FROM NEW.result_digest AND approved_at=NEW.approved_at) THEN
  RAISE EXCEPTION 'plan source is not unchanged approved data' USING ERRCODE='check_violation';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_plan_source BEFORE INSERT ON plan_execution_input FOR EACH ROW EXECUTE FUNCTION check_plan_source();
CREATE FUNCTION apply_plan_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r plan_review; e plan_execution; p plan_candidate;
BEGIN
 SELECT * INTO r FROM plan_review WHERE execution_id=NEW.execution_id FOR UPDATE;
 SELECT * INTO e FROM plan_execution WHERE execution_id=NEW.execution_id;
 SELECT * INTO p FROM plan_candidate WHERE execution_id=NEW.execution_id AND plan_id=NEW.plan_id;
 IF r.status IS DISTINCT FROM NEW.status_before OR r.version IS DISTINCT FROM NEW.review_version OR
    NEW.input_digest IS DISTINCT FROM e.input_digest OR e.status NOT IN ('COMPLETED','PARTIAL') OR p.plan_id IS NULL THEN
  RAISE EXCEPTION 'stale or invalid decision' USING ERRCODE='check_violation';
 END IF;
 IF NOT ((NEW.action='REVIEW' AND r.status='DRAFT' AND NEW.status_after='REVIEW') OR
         (NEW.action='REJECT' AND r.status='REVIEW' AND NEW.status_after='REJECTED' AND r.selected_plan_id=NEW.plan_id) OR
         (NEW.action='APPROVE' AND r.status='REVIEW' AND NEW.status_after='APPROVED' AND r.selected_plan_id=NEW.plan_id)) THEN
  RAISE EXCEPTION 'invalid decision transition' USING ERRCODE='check_violation';
 END IF;
 IF NEW.action='APPROVE' AND (NOT NEW.auth_verified OR e.data_origin<>'REAL_ENGINE' OR p.feasibility<>'FEASIBLE'
   OR e.policy_version IS NULL OR p.policy_ref IS NULL OR jsonb_array_length(e.input_snapshot->'missing_inputs')<>0
   OR jsonb_array_length(e.result_snapshot->'unverified')<>0 OR jsonb_array_length(p.unverified)<>0
   OR jsonb_array_length(NEW.exception_codes)<>0) THEN
  RAISE EXCEPTION 'formal approval prerequisites missing' USING ERRCODE='check_violation';
 END IF;
 UPDATE plan_review SET status=NEW.status_after,selected_plan_id=NEW.plan_id,version=version+1 WHERE execution_id=NEW.execution_id;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_plan_decision BEFORE INSERT ON plan_decision FOR EACH ROW EXECUTE FUNCTION apply_plan_decision();
CREATE FUNCTION guard_plan_review_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF pg_trigger_depth()<2 THEN RAISE EXCEPTION 'review state changes require a decision event' USING ERRCODE='check_violation'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_review_update BEFORE UPDATE ON plan_review FOR EACH ROW EXECUTE FUNCTION guard_plan_review_update();
"""


def upgrade():
    op.execute(DDL)
    immutable = ('plan_execution','plan_candidate','plan_constraint_evaluation','plan_material_requirement','plan_execution_input','plan_decision')
    for table in immutable:
        op.execute(f'CREATE TRIGGER trg_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION forbid_change()')
    for table in ('plan_candidate','plan_constraint_evaluation','plan_material_requirement','plan_execution_input','plan_review'):
        op.execute(f'CREATE TRIGGER trg_{table}_atomic BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION guard_plan_child()')
    op.execute('CREATE TRIGGER trg_review_delete BEFORE DELETE ON plan_review FOR EACH ROW EXECUTE FUNCTION forbid_change()')


def downgrade():
    if op.get_bind().execute(text('SELECT EXISTS(SELECT 1 FROM plan_execution)')).scalar():
        raise RuntimeError('Plan history exists; destructive downgrade refused')
    for table in ('plan_decision','plan_review','plan_execution_input','plan_material_requirement','plan_constraint_evaluation','plan_candidate','plan_execution'):
        op.drop_table(table)
    for name in ('guard_plan_review_update','apply_plan_decision','check_plan_source','verify_plan_rows','guard_plan_child'):
        op.execute(f'DROP FUNCTION {name}()')
