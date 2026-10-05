"""What the model must return for each document.

Sign convention for every transaction amount, on every account type:
negative = money leaving you or debt growing (purchases, bills, interest, fees),
positive = money coming in or debt shrinking (deposits, refunds, card payments).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal[
    "income",
    "rent_housing",
    "utilities",
    "phone_internet",
    "groceries",
    "dining",
    "gas_transport",
    "auto",
    "insurance",
    "subscriptions",
    "shopping",
    "entertainment_leisure",
    "health_medical",
    "personal_care",
    "pets",
    "travel",
    "gifts_donations",
    "personal_private",
    "installment_plan",
    "reimbursement",
    "investing",
    "taxes",
    "moving",
    "debt_payment",
    "transfer_internal",
    "fees_interest",
    "cash_atm",
    "other",
]


class EarningLine(BaseModel):
    description: str
    kind: Literal["regular", "overtime", "holiday", "premium", "leave", "bonus", "other"]
    hours: Optional[float] = None
    amount: float


class DeductionLine(BaseModel):
    description: str
    kind: Literal[
        "federal_tax",
        "state_tax",
        "local_tax",
        "social_security",
        "medicare",
        "retirement",
        "retirement_loan",
        "health_insurance",
        "dental_vision",
        "life_insurance",
        "union_dues",
        "allotment",
        "garnishment",
        "other",
    ]
    amount: float


class LeaveBalance(BaseModel):
    kind: str = Field(description="e.g. annual, sick, comp time")
    balance_hours: Optional[float] = None
    accrued_period: Optional[float] = None
    used_period: Optional[float] = None
    accrued_ytd: Optional[float] = None
    used_ytd: Optional[float] = None
    use_or_lose_date: Optional[str] = None


class EmployerContribution(BaseModel):
    description: str
    amount: float


class PayStatement(BaseModel):
    pay_period_start: Optional[str] = Field(None, description="YYYY-MM-DD")
    pay_period_end: Optional[str] = Field(None, description="YYYY-MM-DD")
    pay_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    gross_pay: float = Field(description="Current-period gross, not year-to-date")
    net_pay: float = Field(description="Current-period net deposited, not year-to-date")
    earnings: list[EarningLine]
    deductions: list[DeductionLine] = Field(description="Current-period amounts only")
    employer_retirement_contribution: Optional[float] = None
    ytd_gross: Optional[float] = None
    leave: list[LeaveBalance]
    hourly_rate: Optional[float] = None
    overtime_rate: Optional[float] = None
    annual_salary: Optional[float] = None
    retirement_percent: Optional[float] = None
    leave_year_end: Optional[str] = Field(None, description="YYYY-MM-DD")
    max_leave_carryover: Optional[float] = None
    employer_contributions: list[EmployerContribution] = []


class Transaction(BaseModel):
    date: str = Field(description="YYYY-MM-DD")
    reference: Optional[str] = Field(None, description="Bank reference number, if any")
    description: str = Field(description="Merchant/description text as printed")
    amount: float = Field(description="Negative = money out or debt up; positive = money in or debt down")
    category: Category
    looks_recurring: bool = Field(description="Subscription, bill, or installment that likely repeats")


class PromoBalance(BaseModel):
    description: str
    balance: Optional[float] = None
    apr: Optional[float] = None
    expires: Optional[str] = Field(None, description="YYYY-MM-DD")
    deferred_interest: Optional[bool] = Field(
        None, description="True if all back-interest is charged when the promo ends unpaid"
    )


class CardTerms(BaseModel):
    credit_limit: Optional[float] = None
    minimum_payment_due: Optional[float] = None
    payment_due_date: Optional[str] = None
    purchase_apr: Optional[float] = None
    cash_advance_apr: Optional[float] = None
    interest_charged: Optional[float] = None
    fees_charged: Optional[float] = None
    promos: list[PromoBalance]


class LoanTerms(BaseModel):
    principal_balance: Optional[float] = None
    interest_rate: Optional[float] = None
    regular_payment: Optional[float] = None
    payment_due_date: Optional[str] = None
    payments_remaining: Optional[int] = None
    maturity_date: Optional[str] = None
    payoff_amount: Optional[float] = None


class AccountStatement(BaseModel):
    institution: str
    account_kind: Literal[
        "checking", "savings", "credit_card", "auto_loan", "personal_loan", "installment", "other"
    ]
    account_last4: Optional[str] = Field(None, description="Last 4 digits if visible, else null")
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    opening_balance: Optional[float] = Field(
        None, description="For cards/loans: amount owed, as a positive number"
    )
    closing_balance: Optional[float] = Field(
        None, description="For cards/loans: amount owed, as a positive number"
    )
    transactions: list[Transaction] = Field(
        description="Every transaction in the period, including interest and fees"
    )
    card: Optional[CardTerms] = None
    loan: Optional[LoanTerms] = None


class DocumentExtraction(BaseModel):
    doc_type: Literal["pay_statement", "account_statement", "other"]
    pay: Optional[PayStatement] = None
    statement: Optional[AccountStatement] = None
    notes: str = Field(description="Anything unclear, unreadable, or ambiguous; empty if none")
