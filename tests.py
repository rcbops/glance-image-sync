import unittest
from rcb import glance_image_sync


class TestGlanceImageSync(unittest.TestCase):
    def test_shorten_long_name(self):
        hostname = 'test.test.com'
        tmp = glance_image_sync._shorten_hostname(hostname)
        self.assertEqual(tmp, 'test')

    def test_shorten_short_name(self):
        hostname = 'test'
        tmp = glance_image_sync._shorten_hostname(hostname)
        self.assertEqual(tmp, 'test')

if __name__ == '__main__':
    unittest.main()
