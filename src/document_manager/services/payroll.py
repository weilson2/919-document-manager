from sqlalchemy import func, select
from sqlalchemy.orm import Session

from document_manager.payroll import PayrollInput, calculate
from document_manager.persistence.database import write_session
from document_manager.persistence.models import Employee, PayrollRun
from document_manager.persistence.repositories import (
    ActivityRepository,
    RecordRepository,
)
from document_manager.services.auth import require_sensitive
from document_manager.services.errors import BusinessError, RecordUnavailable


class PayrollService:
    def __init__(self, engine, identity=None):
        self._engine = engine
        self._identity = identity

    def calculate(self, company_id, employee_id, values):
        require_sensitive(self._identity)
        inputs = PayrollInput.model_validate(values)
        with Session(self._engine) as session:
            self._employee(session, company_id, employee_id)
        # Mapping employee attributes and taxable wages to each Malaysian schedule requires a verified adapter.
        return calculate(inputs, {})

    def save(self, company_id, employee_id, values, *, approve=False):
        require_sensitive(self._identity)
        inputs = PayrollInput.model_validate(values)
        with write_session(self._engine) as session:
            employee = self._employee(session, company_id, employee_id)
            result = calculate(inputs, {})
            if approve and result.blockers:
                raise BusinessError("Approval blocked. " + " ".join(result.blockers))
            position = session.scalar(select(func.max(PayrollRun.revision)).where(
                PayrollRun.company_id == company_id, PayrollRun.employee_id == employee_id,
                PayrollRun.period == inputs.period,
            )) or 0
            run = PayrollRun(
                company_id=company_id, employee_id=employee_id, period=inputs.period, revision=position + 1,
                actor_id=self._identity.id if self._identity else None, status="approved" if approve else "draft",
                inputs=inputs.model_dump(mode="json"), result=result.snapshot(),
                employee_snapshot={
                    "name": employee.name, "number": employee.employee_number, "salary_type": employee.salary_type,
                    "position": employee.position, "citizenship": employee.citizenship,
                    "employment_type": employee.employment_type, "tax_residency": employee.tax_residency,
                    "birth_date": employee.birth_date.isoformat() if employee.birth_date else None,
                },
            )
            session.add(run)
            session.flush()
            ActivityRepository(session, company_id).record(
                "approved" if approve else "saved draft", "payroll", run.id,
                f"{inputs.period:%Y-%m} · Revision {run.revision}",
            )
            return run.id

    def get(self, company_id, run_id):
        require_sensitive(self._identity)
        with Session(self._engine) as session:
            run = RecordRepository(session, company_id, PayrollRun).get(run_id)
            if run is None:
                raise RecordUnavailable("This payroll record is unavailable in the active company.")
            return run

    def list(self, company_id):
        require_sensitive(self._identity)
        with Session(self._engine) as session:
            return list(session.scalars(select(PayrollRun).where(PayrollRun.company_id == company_id)
                                        .order_by(PayrollRun.period.desc(), PayrollRun.id.desc())))

    @staticmethod
    def payslip_values(run):
        return {
            **run.result["amounts"],
            "employee_name": run.employee_snapshot["name"],
            "employee_number": run.employee_snapshot["number"],
            "period": run.period.strftime("%B %Y"),
            "payroll_status": "DRAFT · statutory amounts unverified" if run.status == "draft" else "Approved",
        }

    @staticmethod
    def _employee(session, company_id, employee_id):
        employee = RecordRepository(session, company_id, Employee).get(employee_id)
        if employee is None or employee.archived_at is not None:
            raise RecordUnavailable("Select an available employee in the active company.")
        return employee
