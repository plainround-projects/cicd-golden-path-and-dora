import json
import unittest

from app.main import answer


class AnswerTest(unittest.TestCase):
    def test_health_is_ok(self):
        self.assertEqual(answer("/healthz"), (200, "ok\n"))

    def test_root_names_the_service_and_its_owner(self):
        status, body = answer("/")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["service"], "__NAME__")
        self.assertEqual(json.loads(body)["owner"], "__OWNER__")

    def test_unknown_path_is_404(self):
        self.assertEqual(answer("/nope")[0], 404)


if __name__ == "__main__":
    unittest.main()
