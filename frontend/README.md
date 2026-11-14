# React frontend

Owner: docs/OWNERSHIP.md. Canonical setup and current implementation status: [root README](../README.md).

```powershell
npm ci
npm run dev
npm run type-check
npm run build
npm run test:e2e:ui
```

Actual registration, approval and forecasts use FastAPI. Connection failures never fall back to fixture approvals or forecasts. VITE_API_URL contains only the public API address, never database credentials.

The approved PPT informs the navy header, process navigation, cards, forecast SVG chart and planning workspace. MPS/RCCP/MRP/what-if/final approval are explicitly isolated fixed DEMO views, with calculations and formal approval unavailable. No PPT image is used as an application background.

The workflow now has explicit DEMO and live-module modes. ClassificationPanel supports HOLD/review without batch creation. LivePlanningPanel renders typed read-only module responses when delivered and never switches to DEMO on failure. Server planning persistence, formal approval and what-if base-plan storage remain unavailable. See docs/TEAM_HANDOFF.md in the repository root.

Legacy PlanComparisonScreen/DiagnosisScreen/ApprovalScreen and mocks remain as migration references; active planning routes use PlanningWorkspace. Historical docs/screenshots do not document the current UI.

Browser tests live under root tests/e2e, owned by integration. `npm run test:e2e` resets the dedicated test DB and requires separate human approval and target checks. Read [development workflow](../docs/DEVELOPMENT_WORKFLOW.md) first. `test:e2e:ui` never connects to a DB.
