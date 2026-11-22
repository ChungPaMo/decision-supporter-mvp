"""Formal export reads approved server state only. Test output is separately labelled."""
from io import BytesIO
from openpyxl import Workbook
from app.errors import ApiError,ErrorCode
from app.exports.xlsx import _put_text,_put_number,MAX_ROWS
from .approval import approval_allowed,ApprovalContext

NUMERIC={'p50','p80','p90','production_qty','limit_value','used_value','required_qty','available_qty','shortage_qty','horizon_months'}


def _render(execution,plan,banner):
    wb=Workbook();wb.remove(wb.active)
    wb.properties.title=banner
    output=execution.result_snapshot
    sections={
        'Overview':[{'execution_id':str(execution.execution_id),'plan_id':plan.plan_id,'month':execution.target_month,
                     'calculation_status':execution.status,'review_status':execution.decision_status,'label':plan.label,
                     'horizon_months':str(execution.horizon_months),'end_month':execution.input_snapshot.command.months[-1]}],
        'Forecast':[{'forecast_execution_id':str(execution.forecast_execution_id),**r.model_dump(mode='json')} for r in execution.input_snapshot.forecast_rows],
        'MPS':[r.model_dump(mode='json') for r in plan.production],
        'RCCP':[r.model_dump(mode='json') for r in output.constraint_evaluations if r.plan_id==plan.plan_id],
        'MRP':[r.model_dump(mode='json') for r in output.material_requirements if r.plan_id==plan.plan_id],
        'Exceptions':[r.model_dump(mode='json') for r in [*output.warnings,*output.unverified,*plan.unverified,*output.errors]],
        'Audit':[{'input_digest':execution.input_digest,'result_digest':execution.result_digest,'engine_version':execution.engine_version,
                  'policy_version':execution.policy_version,'data_origin':execution.data_origin},
                 *[r.model_dump(mode='json') for r in execution.decisions],
                 *[r.model_dump(mode='json') for r in execution.input_snapshot.approved_inputs.sources]],
    }
    if sum(len(rows) for rows in sections.values())>MAX_ROWS:
        raise ApiError(413,ErrorCode.EXPORT_TOO_LARGE,'Plan export row limit exceeded.')
    import json
    for name,rows in sections.items():
        ws=wb.create_sheet(name);_put_text(ws,1,1,banner)
        headers=list(dict.fromkeys(k for row in rows for k in row))
        for col,key in enumerate(headers,1): _put_text(ws,2,col,key)
        for line,row in enumerate(rows,3):
            for col,key in enumerate(headers,1):
                value=row.get(key)
                if key in NUMERIC: _put_number(ws,line,col,value)
                else:
                    if isinstance(value,(dict,list)):value=json.dumps(value,ensure_ascii=False)
                    _put_text(ws,line,col,None if value is None else str(value))
        ws.freeze_panes='A3';ws.oddHeader.center.text=banner
    stream=BytesIO();wb.save(stream);return stream.getvalue()


def formal_export(execution):
    plan=next((p for p in execution.result_snapshot.plans if p.plan_id==execution.selected_plan_id),None)
    approved=[e for e in execution.decisions if e.action=='APPROVE' and e.auth_verified]
    if execution.decision_status!='APPROVED' or plan is None or not approved or approved[-1].plan_id!=plan.plan_id:
        raise ApiError(409,ErrorCode.PLAN_EXPORT_BLOCKED,'Only a verified, approved stored plan can be exported.')
    context=ApprovalContext(subject=approved[-1].actor_id,roles=frozenset({'PLAN_APPROVER'}),verified=True,policy_enabled=True)
    approval_allowed(execution,plan,context)
    return _render(execution,plan,'APPROVED / '+str(execution.execution_id))


def test_double_export(execution):
    """Test-only generator; no HTTP endpoint, no approved branding."""
    if execution.data_origin!='TEST_DOUBLE' or not execution.result_snapshot.plans:
        raise ValueError('A quarantined test double is required')
    return _render(execution,execution.result_snapshot.plans[0],'SYNTHETIC / TEST-DOUBLE-ONLY / UNAPPROVED')
