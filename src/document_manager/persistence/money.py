from decimal import Context, Decimal, InvalidOperation

from sqlalchemy import Integer, TypeDecorator

MAX_MYR = Decimal("999999999.99")


def money_to_sen(value: Decimal) -> int:
    if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value <= MAX_MYR:
        raise ValueError(f"Enter a MYR amount between 0 and {MAX_MYR}.")
    context = Context(prec=16)
    try:
        amount = value.quantize(Decimal("0.01"), context=context)
        if value != amount:
            raise ValueError("Enter at most two decimal places.")
    except InvalidOperation:
        raise ValueError("Enter a valid MYR amount.") from None
    return int(amount.scaleb(2, context=context))


def sen_to_money(value: int) -> Decimal:
    return Decimal(f"{value}e-2")


class Money(TypeDecorator):
    """MYR as Decimal in Python and integer sen in SQLite."""

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else money_to_sen(value)

    def process_result_value(self, value, dialect):
        return None if value is None else sen_to_money(value)
