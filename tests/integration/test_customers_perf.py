"""SC-002 / constitution: search stays under 300 ms with 10,000 customers."""

import random
import statistics
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import insert

from floorpro.models import Customer

FIRST = ["Jane", "John", "Amir", "Chloe", "Dev", "Ella", "Femi", "Grace", "Harry", "Isla"]
LAST = ["Smith", "Jones", "Patel", "Brown", "Khan", "Taylor", "Wilson", "Evans", "Clarke", "Hall"]
AREAS = ["BS1", "BS7", "SW1A", "M1", "LS6", "CF10", "EH3", "B15", "NE1", "OX4"]


@pytest.mark.slow
def test_search_10k_customers_under_300ms(client, app, htmx):
    rng = random.Random(42)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(10_000):
        phone = f"07{rng.randrange(100_000_000, 999_999_999)}"
        area = rng.choice(AREAS)
        postcode = f"{area} {rng.randrange(1, 9)}{rng.choice('ABDEFGHJ')}{rng.choice('LNPQRSTU')}"
        trade = i % 7 == 0
        rows.append(
            dict(
                customer_type="trade" if trade else "domestic",
                show_vat_breakdown=trade,
                first_name=rng.choice(FIRST),
                last_name=f"{rng.choice(LAST)}{i}",
                company_name=f"Company {i} Flooring" if trade else None,
                mobile_phone=phone,
                mobile_phone_digits=phone,
                email=f"customer{i}@example.com",
                postcode=postcode,
                postcode_compact=postcode.replace(" ", ""),
                marketing_consent=False,
                is_archived=i % 50 == 0,
                created_at=start + timedelta(minutes=i),
                updated_at=start + timedelta(minutes=i),
            )
        )
    with app.state.sessionmaker.begin() as session:
        session.execute(insert(Customer), rows)

    queries = ["smith", "07123", "BS7", "customer9999@", "C-05000"]
    for q in queries:
        timings = []
        for _ in range(5):
            began = time.perf_counter()
            response = client.get("/customers", params={"q": q}, headers=htmx)
            timings.append(time.perf_counter() - began)
            assert response.status_code == 200
        median = statistics.median(timings)
        assert median < 0.3, f"search {q!r} took {median * 1000:.0f} ms"
