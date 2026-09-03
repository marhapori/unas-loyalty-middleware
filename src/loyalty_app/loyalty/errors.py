from __future__ import annotations


class LoyaltyServiceError(RuntimeError):
    """Base class for loyalty-service-level failures with a stable machine code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CustomerNotFound(LoyaltyServiceError):
    def __init__(self) -> None:
        super().__init__("customer_not_found", "Ismeretlen vagy ervenytelen QR-kod")


class TransactionInFlight(LoyaltyServiceError):
    def __init__(self) -> None:
        super().__init__(
            "transaction_in_flight",
            "Ez a tranzakcio meg feldolgozas alatt van, probald ujra par masodperc mulva",
        )


class TransactionNotFound(LoyaltyServiceError):
    def __init__(self) -> None:
        super().__init__("transaction_not_found", "A tranzakcio nem talalhato")


class TransactionAlreadyReversed(LoyaltyServiceError):
    def __init__(self) -> None:
        super().__init__("already_reversed", "Ez a tranzakcio mar vissza lett vonva")


class TransactionNotReversible(LoyaltyServiceError):
    def __init__(self, reason: str) -> None:
        super().__init__("not_reversible", f"A tranzakcio nem vonhato vissza: {reason}")


class UnasWriteUncertain(LoyaltyServiceError):
    """The UNAS balance write timed out / errored transiently - outcome unknown.

    The transaction stays 'pending' in the DB and must be reconciled by the
    background worker before a retry with the same idempotency key is accepted.
    """

    def __init__(self) -> None:
        super().__init__(
            "write_uncertain",
            "A UNAS valasza bizonytalan volt, az egyenleg egyeztetese folyamatban van",
        )


class UnasWriteFailed(LoyaltyServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__("unas_write_failed", f"UNAS hiba: {detail}")
