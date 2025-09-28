"""
간단한 테스트 사용자 생성 스크립트 (Django shell 전용)

사용 방법:
1. Django shell 실행: python manage.py shell
2. 다음 명령 실행: exec(open('locust_test/create_users_simple.py').read())
"""

from django.contrib.auth.models import User
from django.db import transaction

def create_test_users(count=10000, batch_size=1000):
    """테스트 사용자 생성 함수"""
    print(f"📝 {count:,}명의 테스트 사용자 생성을 시작합니다...")

    # 기존 사용자 수 확인
    existing_count = User.objects.filter(username__startswith='user').count()
    print(f"📊 기존 테스트 사용자: {existing_count:,}명")

    if existing_count >= count:
        print(f"✅ 이미 {existing_count:,}명의 사용자가 존재합니다.")
        return existing_count

    # 부족한 사용자 수 계산
    users_to_create = count - existing_count
    print(f"🚀 {users_to_create:,}명의 추가 사용자를 생성합니다...")

    created_count = 0

    # 배치 단위로 사용자 생성
    for start_idx in range(existing_count, count, batch_size):
        end_idx = min(start_idx + batch_size, count)
        batch_users = []

        for i in range(start_idx, end_idx):
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
                    progress = (created_count / users_to_create * 100)
                    print(f"⏳ {created_count:,}/{users_to_create:,} 사용자 생성 중... ({progress:.1f}%)")
            except Exception as e:
                print(f"❌ 배치 생성 실패: {e}")
                continue

    # 최종 결과 확인
    total_users = User.objects.filter(username__startswith='user').count()
    print(f"✅ 총 {total_users:,}명의 테스트 사용자가 생성되었습니다!")
    print(f"📈 이번 실행에서 {created_count:,}명의 새 사용자가 추가되었습니다.")

    # 샘플 사용자 확인
    sample_users = User.objects.filter(username__startswith='user')[:3]
    print("\n📋 생성된 사용자 샘플:")
    for user in sample_users:
        print(f"  - {user.username} (ID: {user.id})")

    return total_users

# 자동 실행
if __name__ == "__main__":
    print("🚀 Traffic Django 테스트 사용자 생성")
    print("=" * 50)

    total = create_test_users()

    print(f"\n✅ 완료! 총 {total:,}명의 사용자가 준비되었습니다.")
    print("📝 Locust 테스트 실행: poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000")
else:
    # Django shell에서 실행될 때
    total = create_test_users()
    print(f"\n✅ 완료! 총 {total:,}명의 사용자가 준비되었습니다.")
    print("📝 Locust 테스트 실행: poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000")