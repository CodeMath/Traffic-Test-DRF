"""
상품 관련 캐시 매니저
"""

import hashlib
import json
import logging

from django.core.cache import cache
from django.http import QueryDict

logger = logging.getLogger(__name__)


class ProductCacheManager:
    """
    상품 관련 캐시 매니저
    """

    CACHE_PREFIX = "product"
    DEFAULT_TTL = 600

    # 명시적으로 키에 포함할 필터 (디버깅 용이성)
    EXPLICIT_FILTERS = ["status", "category"]

    KEYS = {
        "list": "{prefix}:list:{page}:{limit}:{filters}",
        "detail": "{prefix}:detail:{product_id}",
        "stock": "{prefix}:stock:{product_id}",
    }

    @classmethod
    def _build_key(cls, key_type, **params):
        """캐시 키 생성"""
        template = cls.KEYS[key_type]
        return template.format(prefix=cls.CACHE_PREFIX, **params)

    @classmethod
    def _normalize_filters(cls, filters):
        """
        QueryDict를 정규화된 딕셔너리로 변환

        Args:
            filters: QueryDict 또는 dict

        Returns:
            정규화된 dict
        """
        if isinstance(filters, QueryDict):
            # QueryDict를 일반 dict로 변환 (리스트 제거)
            normalized = {}
            for key, value in filters.items():
                # 페이지네이션 파라미터 제외 (이미 명시적으로 처리)
                if key in ["page", "limit"]:
                    continue
                # 리스트인 경우 첫 번째 값만 사용
                normalized[key] = value[0] if isinstance(value, list) else value
        else:
            normalized = {k: v for k, v in filters.items() if k not in ["page", "limit"]}

        return normalized

    @classmethod
    def _build_filter_key(cls, filters):
        """
        필터를 캐시 키 문자열로 변환 (하이브리드 방식)

        Example:
            {'status': 'active', 'category': 'phone', 'search': 'iphone'}
            → 'status=active:category=phone:3a4b5c6d'

        Args:
            filters: QueryDict 또는 dict

        Returns:
            필터 키 문자열
        """
        normalized = cls._normalize_filters(filters)

        if not normalized:
            return "all"

        key_parts = []

        # 1. 명시적 필터 (가독성)
        explicit_parts = []
        for filter_name in cls.EXPLICIT_FILTERS:
            if filter_name in normalized:
                value = normalized[filter_name]
                explicit_parts.append(f"{filter_name}={value}")

        if explicit_parts:
            key_parts.extend(explicit_parts)

        # 2. 나머지 필터는 해시 (길이 제어)
        other_filters = {k: v for k, v in normalized.items() if k not in cls.EXPLICIT_FILTERS}
        if other_filters:
            filters_hash = cls._hash_dict(other_filters)
            key_parts.append(filters_hash[:8])  # 8자 해시

        return ":".join(key_parts) if key_parts else "all"

    @classmethod
    def _hash_dict(cls, data):
        """
        딕셔너리를 일관된 MD5 해시로 변환

        Args:
            data: dict

        Returns:
            MD5 해시 문자열 (16진수)
        """
        # 키로 정렬하여 일관성 보장
        sorted_data = dict(sorted(data.items()))

        # JSON 문자열로 변환 (일관성 보장)
        data_str = json.dumps(sorted_data, sort_keys=True, ensure_ascii=False)

        # MD5 해시 (빠르고 충분히 안전)
        return hashlib.md5(data_str.encode("utf-8")).hexdigest()

    @classmethod
    def get_list(cls, page: int, limit: int, filters) -> dict | None:
        """
        상품 목록 캐시 조회

        Args:
            page: 페이지 번호
            limit: 페이지 크기
            filters: QueryDict 또는 dict

        Returns:
            캐시된 데이터 또는 None
        """
        filter_key = cls._build_filter_key(filters)
        cache_key = cls._build_key("list", page=page, limit=limit, filters=filter_key)
        print(cache_key)
        logger.info(f"목록 캐시 조회: {cache_key}")
        return cache.get(cache_key)

    @classmethod
    def set_list(cls, page: int, limit: int, filters, data: list, ttl=None) -> str:
        """
        상품 목록 캐시 설정

        Args:
            page: 페이지 번호
            limit: 페이지 크기
            filters: QueryDict 또는 dict
            data: 캐시할 데이터
            ttl: 캐시 유효 시간 (초)

        Returns:
            생성된 캐시 키
        """
        filter_key = cls._build_filter_key(filters)
        cache_key = cls._build_key("list", page=page, limit=limit, filters=filter_key)
        cache.set(cache_key, data, timeout=ttl or cls.DEFAULT_TTL)
        logger.info(f"목록 캐시 설정: {cache_key}")
        return cache_key

    @classmethod
    def invalidate_list(cls):
        """목록 캐시 무효화 (상품 생성/수정/삭제 시)"""
        pattern = f"{cls.CACHE_PREFIX}:list:*"
        logger.info(f"목록 캐시 무효화: {pattern}")
        cache.delete_pattern(pattern)
