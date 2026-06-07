import base64
import time
import unittest

from src.models import RunRequest, UploadedDocument
from src.orchestrator import ResearchOrchestrator


class OrchestratorTests(unittest.TestCase):
    def test_runs_three_stocks_and_document_to_completion(self):
        orchestrator = ResearchOrchestrator()
        document = UploadedDocument(
            name="notes.txt",
            content_base64=base64.b64encode("风险：竞争加剧。收入增长。".encode()).decode(),
        )
        run = orchestrator.create_run(
            RunRequest(query="比较英伟达、阿里巴巴和英特尔最近三个月", documents=[document])
        )
        for _ in range(100):
            state = orchestrator.get_run(run.run_id)
            if state.status in ("completed", "partial", "failed"):
                break
            time.sleep(0.02)

        self.assertEqual(state.status, "completed")
        self.assertEqual(list(state.stocks), ["NVDA", "BABA", "INTC"])
        self.assertTrue(state.report_markdown)
        self.assertEqual(state.document_results[0]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
