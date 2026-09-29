"""Bo‘sh natijadan dashboard yasalmaydi — javob sababini ochiq aytadi."""

from typing import Any

from tests.fake_core import default_data
from tests.unit.test_fake_documents import drive


async def test_empty_result_does_not_create_dashboard() -> None:
    data = default_data()
    data["run_metric_query"]["rows"] = []

    def tools(name: str, args: dict[str, Any]) -> dict[str, Any]:
        return data[name]

    calls, response = await drive("Ali, 2026 yanvar savdosini dashboard qil", tools,
                                  role="sales_analyst")
    assert "create_dashboard" not in [n for n, _ in calls]
    assert "Dashboard yaratilmadi" in response.text
