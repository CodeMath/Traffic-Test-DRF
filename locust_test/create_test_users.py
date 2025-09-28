#!/usr/bin/env python3
"""
테스트 사용자 생성 스크립트

이 스크립트는 Locust 부하 테스트를 위한 10,000개의 테스트 사용자를 생성합니다.
사용자명: user0, user1, user2, ..., user9999
비밀번호: 모두 'password'

실행 방법:
1. Django shell에서 실행 (권장)
   python manage.py shell
   exec(open('locust_test/create_test_users.py').read())

2. 직접 실행
   DJANGO_SETTINGS_MODULE=config.settings python locust_test/create_test_users.py
"""

import os
import sys
from pathlib import Path

import django

# Django 설정 초기화
if __name__ == "__main__":
    # 프로젝트 루트 디렉터리를 sys.path에 추가
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

    # Django 설정
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    django.setup()

    from django.contrib.auth.models import User
    from django.db import transaction

    def create_test_users(count: int = 10000, batch_size: int = 1000):
        """테스트 사용자 생성"""
        print(f"📝 {count:,}명의 테스트 사용자 생성을 시작합니다...")

        # 기존 사용자 수 확인
        existing_count = User.objects.filter(username__startswith='user').count()
        print(f"📊 기존 테스트 사용자: {existing_count:,}명")

        # 이미 충분한 사용자가 있는지 확인
        if existing_count >= count:
            print(f"✅ 이미 {existing_count:,}명의 사용자가 존재합니다. 추가 생성을 건너뜁니다.")
            return

        # 부족한 사용자 수 계산
        users_to_create = count - existing_count
        print(f"🚀 {users_to_create:,}명의 추가 사용자를 생성합니다...")

        created_count = 0

        # 배치 단위로 사용자 생성
        for start_idx in range(existing_count, count, batch_size):
            end_idx = min(start_idx + batch_size, count)
            batch_users = []

            for i in range(start_idx, end_idx):
                # 사용자명 중복 체크 (안전장치)
                username = f"user{i}"
                if not User.objects.filter(username=username).exists():
                    user = User(username=username, email=f"{username}@test.com")
                    user.set_password("password")
                    batch_users.append(user)

            # 배치 생성
            if batch_users:
                try:
                    with transaction.atomic():
                        User.objects.bulk_create(batch_users, ignore_conflicts=True)
                        created_count += len(batch_users)
                        print(f"⏳ {created_count:,}/{users_to_create:,} 사용자 생성 중... "
                              f"({(created_count/users_to_create*100):.1f}%)")
                except Exception as e:
                    print(f"❌ 배치 생성 실패: {e}")
                    continue

        # 최종 결과 확인
        total_users = User.objects.filter(username__startswith='user').count()
        print(f"✅ 총 {total_users:,}명의 테스트 사용자가 생성되었습니다!")
        print(f"📈 이번 실행에서 {created_count:,}명의 새 사용자가 추가되었습니다.")

        # 샘플 사용자 확인
        sample_users = User.objects.filter(username__startswith='user')[:5]
        print("\n📋 생성된 사용자 샘플:")
        for user in sample_users:
            print(f"  - {user.username} (ID: {user.id})")

        return total_users

    def verify_test_users():
        """테스트 사용자 검증"""
        print("🔍 테스트 사용자 검증 중...")

        total_count = User.objects.filter(username__startswith='user').count()
        print(f"📊 총 사용자 수: {total_count:,}명")

        # 패스워드 검증 (샘플)
        test_user = User.objects.filter(username='user0').first()
        if test_user and test_user.check_password('password'):
            print("✅ 비밀번호 검증 성공")
        else:
            print("❌ 비밀번호 검증 실패")

        return total_count >= 10000

    def cleanup_test_users():
        """테스트 사용자 정리 (선택적)"""
        response = input("⚠️ 모든 테스트 사용자를 삭제하시겠습니까? (y/N): ")
        if response.lower() == 'y':
            count = User.objects.filter(username__startswith='user').count()
            User.objects.filter(username__startswith='user').delete()
            print(f"🗑️ {count:,}명의 테스트 사용자가 삭제되었습니다.")
        else:
            print("❌ 삭제가 취소되었습니다.")

    # 메인 실행
    print("🚀 Traffic Django 테스트 사용자 생성 도구")
    print("=" * 50)

    try:
        # 사용자 생성
        total_users = create_test_users()

        # 검증
        if verify_test_users():
            print("✅ 모든 검증을 통과했습니다!")
            print("\n📝 다음 명령어로 Locust 테스트를 실행할 수 있습니다:")
            print("poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000")
        else:
            print("❌ 검증에 실패했습니다.")

    except KeyboardInterrupt:
        print("\n⏹️ 사용자 생성이 중단되었습니다.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()