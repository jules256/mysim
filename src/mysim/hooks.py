"""Hook types defining the annual lifecycle pipeline stages."""

from enum import Enum, auto


class HookType(Enum):
    """Sequential pipeline hooks executed for every simulation year."""

    PRE_PROCESS = auto()
    PROCESS_INFLOWS = auto()
    PROCESS_OUTFLOWS = auto()
    PRE_TAX_SUMMARY = auto()
    CALCULATE_TAX_AND_INSURANCE = auto()
    POST_PROCESS = auto()
    RECONCILE_CASHFLOW = auto()


# Canonical execution order
HOOK_ORDER = [
    HookType.PRE_PROCESS,
    HookType.PROCESS_INFLOWS,
    HookType.PROCESS_OUTFLOWS,
    HookType.PRE_TAX_SUMMARY,
    HookType.CALCULATE_TAX_AND_INSURANCE,
    HookType.POST_PROCESS,
    HookType.RECONCILE_CASHFLOW,
]
