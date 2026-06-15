from __future__ import annotations

import unittest
from unittest.mock import patch

from app.utils.S3Util import S3Util, settings as s3_settings


def _build_s3_util(*, bucket_name: str = "issueissyu-test", region_name: str = "ap-northeast-2") -> S3Util:
    s3_util = S3Util.__new__(S3Util)
    s3_util.bucket_name = bucket_name
    s3_util.region_name = region_name
    return s3_util


class S3UtilPublicUrlTest(unittest.TestCase):
    def test_build_public_file_url_uses_cdn_when_enabled(self) -> None:
        s3_util = _build_s3_util()

        with (
            patch.object(s3_settings, "cdn_enabled", True),
            patch.object(s3_settings, "cdn_base_url", "https://cdn.example.com"),
        ):
            url = s3_util._build_public_file_url("contest-cardnews/1/slide_01.png")

        self.assertEqual(url, "https://cdn.example.com/contest-cardnews/1/slide_01.png")

    def test_build_public_file_url_trims_cdn_trailing_slash(self) -> None:
        s3_util = _build_s3_util()

        with (
            patch.object(s3_settings, "cdn_enabled", True),
            patch.object(s3_settings, "cdn_base_url", "https://cdn.example.com/"),
        ):
            url = s3_util._build_public_file_url("/contest-cardnews/1/slide_01.png")

        self.assertEqual(url, "https://cdn.example.com/contest-cardnews/1/slide_01.png")

    def test_build_public_file_url_falls_back_to_s3_when_cdn_disabled(self) -> None:
        s3_util = _build_s3_util()

        with (
            patch.object(s3_settings, "cdn_enabled", False),
            patch.object(s3_settings, "cdn_base_url", "https://cdn.example.com"),
        ):
            url = s3_util._build_public_file_url("contest-cardnews/1/slide_01.png")

        self.assertEqual(
            url,
            "https://issueissyu-test.s3.ap-northeast-2.amazonaws.com/contest-cardnews/1/slide_01.png",
        )

    def test_build_public_file_url_falls_back_to_s3_when_cdn_base_url_missing(self) -> None:
        s3_util = _build_s3_util()

        with (
            patch.object(s3_settings, "cdn_enabled", True),
            patch.object(s3_settings, "cdn_base_url", None),
        ):
            url = s3_util._build_public_file_url("contest-cardnews/1/slide_01.png")

        self.assertEqual(
            url,
            "https://issueissyu-test.s3.ap-northeast-2.amazonaws.com/contest-cardnews/1/slide_01.png",
        )


if __name__ == "__main__":
    unittest.main()
