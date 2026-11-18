from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from pydantic import Field, model_validator

from document_manager.services.errors import BusinessError
from document_manager.services.validation import DateValue, MoneyValue, ValidatedInput

ZERO = Decimal("0.00")
EARNINGS = ("basic", "overtime", "allowances", "bonus", "commission", "other_earnings")
OTHER_DEDUCTIONS = ("advance", "other_deductions")
STATUTORY = ("epf", "socso", "eis", "pcb")
STATUTORY_LABELS = {"epf": "EPF", "socso": "SOCSO", "eis": "EIS", "pcb": "PCB / MTD"}


class ManualAdjustment(ValidatedInput):
    employee: MoneyValue = ZERO
    employer: MoneyValue = ZERO
    reason: str = Field(min_length=3, max_length=500)


class PayrollInput(ValidatedInput):
    period: DateValue
    basic: MoneyValue
    overtime: MoneyValue = ZERO
    allowances: MoneyValue = ZERO
    bonus: MoneyValue = ZERO
    commission: MoneyValue = ZERO
    other_earnings: MoneyValue = ZERO
    advance: MoneyValue = ZERO
    other_deductions: MoneyValue = ZERO
    adjustments: dict[str, ManualAdjustment] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_period_and_codes(self):
        if self.period.day != 1:
            raise ValueError("Choose the first day of the payroll month.")
        if self.adjustments.keys() - set(STATUTORY):
            raise ValueError("Unknown statutory contribution.")
        if "pcb" in self.adjustments and self.adjustments["pcb"].employer:
            raise ValueError("PCB does not accept an employer amount in this draft.")
        return self


@dataclass(frozen=True)
class ContributionBand:
    lower: Decimal
    upper: Decimal
    employee: Decimal
    employer: Decimal


@dataclass(frozen=True)
class ContributionSchedule:
    code: str
    version: str
    source: str
    starts: date
    ends: date | None
    categories: dict[str, tuple[ContributionBand, ...]]
    not_applicable: dict[str, str] = field(default_factory=dict)

    def amount(self, category, wage):
        if category in self.not_applicable:
            if not self.not_applicable[category].strip():
                raise BusinessError("An eligibility result requires a documented rule.")
            return ZERO, ZERO, "NOT_APPLICABLE", self.not_applicable[category]
        matches = [band for band in self.categories.get(category, ()) if band.lower <= wage <= band.upper]
        if len(matches) != 1:
            raise BusinessError("The statutory wage is outside the available contribution schedule.")
        band = matches[0]
        return band.employee, band.employer, "AUTO", ""


@dataclass(frozen=True)
class RuleOutcome:
    employee: Decimal | None
    employer: Decimal | None
    mode: str
    source: str = ""
    version: str = ""
    reason: str = ""


@dataclass(frozen=True)
class PayrollResult:
    amounts: dict[str, Decimal | None]
    statutory: dict[str, RuleOutcome]
    blockers: tuple[str, ...]

    def snapshot(self):
        return {
            "amounts": {key: format(value, ".2f") if value is not None else None for key, value in self.amounts.items()},
            "statutory": {
                code: {"mode": row.mode, "source": row.source, "version": row.version, "reason": row.reason,
                       "employee": str(row.employee) if row.employee is not None else None,
                       "employer": str(row.employer) if row.employer is not None else None}
                for code, row in self.statutory.items()
            },
            "blockers": list(self.blockers),
        }


# Only audited official schedules may be shipped here. A source URL alone does not verify an implementation.
VERIFIED_SCHEDULES: tuple[ContributionSchedule, ...] = ()


def calculate(
    inputs: PayrollInput, eligibility: dict[str, tuple[str, Decimal]],
    schedules: tuple[ContributionSchedule, ...] = VERIFIED_SCHEDULES,
) -> PayrollResult:
    amounts = {key: getattr(inputs, key) for key in EARNINGS + OTHER_DEDUCTIONS}
    amounts["gross"] = sum((amounts[key] for key in EARNINGS), ZERO)
    outcomes, blockers = {}, []
    for code in STATUTORY:
        versions = [schedule for schedule in schedules if schedule.code == code and schedule.starts <= inputs.period
                    and (schedule.ends is None or inputs.period <= schedule.ends)]
        version = versions[0] if len(versions) == 1 else None
        if override := inputs.adjustments.get(code):
            outcomes[code] = RuleOutcome(override.employee, override.employer, "MANUAL_ADJUSTMENT", reason=override.reason)
            blockers.append(f"{STATUTORY_LABELS[code]} has a manual draft adjustment.")
        elif version is None:
            blockers.append(f"{STATUTORY_LABELS[code]} needs a verified rule for this period.")
            outcomes[code] = RuleOutcome(None, None, "AUTO")
        elif code not in eligibility:
            blockers.append(f"{STATUTORY_LABELS[code]} needs resolved employee eligibility and assessable wages.")
            outcomes[code] = RuleOutcome(None, None, "AUTO", version.source, version.version)
        else:
            try:
                employee, employer, mode, reason = version.amount(*eligibility[code])
                outcomes[code] = RuleOutcome(employee, employer, mode, version.source, version.version, reason)
            except BusinessError as error:
                blockers.append(f"{STATUTORY_LABELS[code]} · {error}")
                outcomes[code] = RuleOutcome(None, None, "AUTO", version.source, version.version)
        row = outcomes[code]
        amounts["pcb" if code == "pcb" else f"employee_{code}"] = row.employee
        if code != "pcb":
            amounts[f"employer_{code}"] = row.employer

    deductions = sum((amounts[key] for key in OTHER_DEDUCTIONS), ZERO)
    deductions += sum((row.employee or ZERO for row in outcomes.values()), ZERO)
    employer = sum((row.employer or ZERO for row in outcomes.values()), ZERO)
    amounts.update(deductions=deductions, net=amounts["gross"] - deductions, employer_cost=amounts["gross"] + employer)
    if amounts["net"] < ZERO:
        blockers.append("Deductions exceed gross pay.")
    return PayrollResult(amounts, outcomes, tuple(blockers))
