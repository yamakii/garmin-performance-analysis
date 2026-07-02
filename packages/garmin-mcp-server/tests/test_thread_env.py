"""Tests that BLAS/OpenMP thread pools are capped for the test session.

Guards the sandbox thread-exhaustion flake (`can't start new thread` /
`OpenBLAS blas_thread_init: pthread_create failed`) fixed in issue #740 by
setting single-threaded env vars at the top of conftest before numpy import.
"""

import os

import pytest


@pytest.mark.unit
@pytest.mark.parametrize(
    "env_var",
    ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"],
)
def test_thread_env_capped(env_var: str) -> None:
    """conftest caps BLAS/OpenMP thread pools to 1 for the session."""
    assert os.environ[env_var] == "1"
