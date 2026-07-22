"""
Math utility helpers (TEST-16).

divide() intentionally performs no zero-division handling, per the ticket's
acceptance criteria - callers get Python's native ZeroDivisionError if b == 0.
"""


def divide(a, b):
    return a / b
