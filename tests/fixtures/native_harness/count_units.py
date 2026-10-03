"""Tiny functional fixture; not an application or field intervention."""


def count_units(batches):
    """Total nonnegative integer batches, rejecting booleans and other inputs."""
    if any(type(value) is not int or value < 0 for value in batches):
        raise ValueError("batches must be nonnegative integers")
    return sum(batches)
