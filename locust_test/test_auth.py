#!/usr/bin/env python3
"""
JWT 인증 테스트 스크립트

Locust 실행 전에 JWT 인증이 올바르게 동작하는지 확인하는 스크립트입니다.
"""

import requests
import json


def test_jwt_auth(base_url="http://localhost:8000"):
    """JWT 인증 테스트"""
    print("🔐 JWT 인증 테스트 시작...")

    # 1. 토큰 발급 테스트
    auth_url = f"{base_url}/api/token/"
    auth_data = {
        "username": "user0",  # 첫 번째 테스트 사용자
        "password": "password"
    }

    print(f"📍 인증 요청: {auth_url}")
    print(f"📋 인증 데이터: {auth_data}")

    try:
        auth_response = requests.post(auth_url, json=auth_data)
        print(f"🔍 응답 상태: {auth_response.status_code}")

        if auth_response.status_code == 200:
            token_data = auth_response.json()
            access_token = token_data.get("access")
            print(f"✅ 토큰 발급 성공")
            print(f"🎫 액세스 토큰: {access_token[:50]}...")

            # 2. 인증이 필요한 API 테스트
            headers = {"Authorization": f"Bearer {access_token}"}

            # 상품 목록 조회 테스트
            products_url = f"{base_url}/api/products/"
            print(f"\n📍 상품 목록 요청: {products_url}")

            products_response = requests.get(products_url, headers=headers)
            print(f"🔍 응답 상태: {products_response.status_code}")

            if products_response.status_code == 200:
                products_data = products_response.json()
                products = products_data.get("results", [])
                print(f"✅ 상품 목록 조회 성공 ({len(products)}개 상품)")

                if products:
                    first_product = products[0]
                    product_id = first_product["id"]
                    print(f"📦 첫 번째 상품: {first_product['name']} (ID: {product_id})")

                    # 3. 재고 가용성 체크 테스트
                    stock_url = f"{base_url}/api/products/stock/available/?product_id={product_id}"
                    print(f"\n📍 재고 조회 요청: {stock_url}")

                    stock_response = requests.get(stock_url, headers=headers)
                    print(f"🔍 응답 상태: {stock_response.status_code}")

                    if stock_response.status_code == 200:
                        stock_data = stock_response.json()
                        stock_results = stock_data.get("results", [])
                        print(f"✅ 재고 조회 성공")

                        if stock_results:
                            stock_info = stock_results[0]
                            available_stock = stock_info.get("available_stock", 0)
                            print(f"📊 가용 재고: {available_stock}개")

                            # 4. 재고 예약 테스트
                            if available_stock > 0:
                                reserve_url = f"{base_url}/api/products/stock/reserve/"
                                reserve_data = {
                                    "product_id": product_id,
                                    "quantity": 1
                                }

                                print(f"\n📍 재고 예약 요청: {reserve_url}")
                                print(f"📋 예약 데이터: {reserve_data}")

                                reserve_response = requests.post(reserve_url, json=reserve_data, headers=headers)
                                print(f"🔍 응답 상태: {reserve_response.status_code}")

                                if reserve_response.status_code == 201:
                                    reserve_result = reserve_response.json()
                                    if reserve_result.get('success', False):
                                        print("✅ 재고 예약 성공")
                                        if reserve_result.get('reservation'):
                                            reservation_info = reserve_result['reservation']
                                            print(f"📦 예약 ID: {reservation_info.get('id')}")
                                            print(f"📊 예약 수량: {reservation_info.get('quantity')}")
                                        print(f"📋 전체 응답: {json.dumps(reserve_result, indent=2, ensure_ascii=False)}")
                                    else:
                                        print(f"⚠️ 예약 실패: {reserve_result.get('error_message', '알 수 없는 오류')}")
                                        print(f"🔍 오류 코드: {reserve_result.get('error_code', 'UNKNOWN')}")
                                else:
                                    print(f"❌ 재고 예약 실패: {reserve_response.text}")
                            else:
                                print("⚠️ 재고가 부족하여 예약 테스트를 건너뜁니다.")
                        else:
                            print("❌ 재고 정보가 없습니다.")
                    else:
                        print(f"❌ 재고 조회 실패: {stock_response.text}")
                else:
                    print("❌ 상품이 없습니다. 먼저 상품을 생성해주세요.")
            else:
                print(f"❌ 상품 목록 조회 실패: {products_response.text}")
        else:
            print(f"❌ 토큰 발급 실패: {auth_response.text}")

    except requests.exceptions.ConnectionError:
        print("❌ 서버에 연결할 수 없습니다. Django 서버가 실행 중인지 확인해주세요.")
        print("💡 서버 실행: python manage.py runserver")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")


def check_test_user():
    """테스트 사용자 존재 확인"""
    print("\n👤 테스트 사용자 확인...")

    try:
        import os
        import sys
        import django
        from pathlib import Path

        # Django 설정
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        django.setup()

        from django.contrib.auth.models import User

        test_user = User.objects.filter(username='user0').first()
        if test_user:
            print(f"✅ 테스트 사용자 'user0' 존재 확인")
            if test_user.check_password('password'):
                print("✅ 비밀번호 확인")
            else:
                print("❌ 비밀번호 불일치")
        else:
            print("❌ 테스트 사용자 'user0'가 없습니다.")
            print("💡 사용자 생성: python manage.py create_test_users")

    except Exception as e:
        print(f"⚠️ Django 연결 실패: {e}")
        print("💡 환경변수 확인: DJANGO_SETTINGS_MODULE=config.settings")


if __name__ == "__main__":
    print("🚀 Locust 테스트 준비 상태 확인")
    print("=" * 50)

    check_test_user()
    test_jwt_auth()

    print("\n🎯 테스트 완료!")
    print("💡 모든 테스트가 성공하면 Locust를 실행할 수 있습니다:")
    print("poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000")