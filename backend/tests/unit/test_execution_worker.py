from unittest import TestCase

from app.workers.celery_app import celery_app


class ExecutionWorkerRoutingTests(TestCase):
    def test_execution_does_not_share_the_research_data_queue(self):
        router = celery_app.amqp.router
        execution_queue = router.route({}, "paper_fund.cycle")["queue"].name
        for task in ("radar.scan", "news.poll", "price_refresh.run"):
            with self.subTest(task=task):
                data_queue = router.route({}, task)["queue"].name
                self.assertNotEqual(execution_queue, data_queue)
        self.assertEqual(execution_queue, "execution")
