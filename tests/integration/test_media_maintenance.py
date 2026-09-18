import os

import pytest

from app.database.maintenance import acquire_api_lease, media_maintenance_snapshot
from app.database.migration_runner import apply_pending_migrations

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DATABASE_INTEGRATION_TESTS") != "1",
    reason="PostgreSQL integration tests are not enabled.",
)


def test_maintenance_and_api_lifetimes_are_mutually_exclusive():
    apply_pending_migrations()
    lease = acquire_api_lease()
    try:
        with pytest.raises(RuntimeError, match="Stop every API"):
            with media_maintenance_snapshot():
                pytest.fail("Cleanup must not run alongside an API instance")
    finally:
        lease.close()
    with media_maintenance_snapshot() as references:
        assert isinstance(references, list)
        with pytest.raises(RuntimeError, match="maintenance is active"):
            acquire_api_lease()
    acquire_api_lease().close()
