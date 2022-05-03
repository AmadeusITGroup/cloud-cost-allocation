# coding: utf-8

class CycleException(Exception):
    """
    Raised when a cost allocation cycle is detected
    """
    pass


class BreakableCycleException(Exception):
    """
    Raised when a breakable cost allocation cycle is detected
    """
    pass


class UnbreakableCycleException(Exception):
    """
    Raised when an unbreakable cost allocation cycle is detected
    """
    pass
