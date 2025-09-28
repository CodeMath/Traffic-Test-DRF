"""
Django management command for creating test users for Locust load testing
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Create test users for Locust load testing"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=10000, help="Number of users to create (default: 10000)")
        parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for bulk creation (default: 1000)")
        parser.add_argument("--cleanup", action="store_true", help="Delete all test users before creating new ones")

    def handle(self, *args, **options):
        count = options["count"]
        batch_size = options["batch_size"]
        cleanup = options["cleanup"]

        self.stdout.write(self.style.SUCCESS("🚀 Traffic Django 테스트 사용자 생성 도구"))
        self.stdout.write("=" * 50)

        # 기존 사용자 정리
        if cleanup:
            self.cleanup_users()

        # 사용자 생성
        self.create_users(count, batch_size)

        # 검증
        self.verify_users(count)

        self.stdout.write(self.style.SUCCESS("\n✅ 테스트 사용자 생성이 완료되었습니다!"))
        self.stdout.write("📝 Locust 테스트 실행: poetry run locust -f locust_test/locustfile.py --host=http://localhost:8000")

    def cleanup_users(self):
        """기존 테스트 사용자 삭제"""
        existing_count = User.objects.filter(username__startswith="user").count()
        if existing_count > 0:
            self.stdout.write(f"🗑️ 기존 {existing_count:,}명의 테스트 사용자를 삭제합니다...")
            User.objects.filter(username__startswith="user").delete()
            self.stdout.write(self.style.SUCCESS("✅ 기존 사용자 삭제 완료"))

    def create_users(self, count: int, batch_size: int):
        """테스트 사용자 생성"""
        self.stdout.write(f"📝 {count:,}명의 테스트 사용자 생성을 시작합니다...")

        # 기존 사용자 수 확인
        existing_count = User.objects.filter(username__startswith="user").count()
        self.stdout.write(f"📊 기존 테스트 사용자: {existing_count:,}명")

        # 이미 충분한 사용자가 있는지 확인
        if existing_count >= count:
            self.stdout.write(self.style.SUCCESS(f"✅ 이미 {existing_count:,}명의 사용자가 존재합니다. 추가 생성을 건너뜁니다."))
            return

        # 부족한 사용자 수 계산
        users_to_create = count - existing_count
        self.stdout.write(f"🚀 {users_to_create:,}명의 추가 사용자를 생성합니다...")

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
                        progress = created_count / users_to_create * 100
                        self.stdout.write(f"⏳ {created_count:,}/{users_to_create:,} 사용자 생성 중... ({progress:.1f}%)")
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"❌ 배치 생성 실패: {e}"))
                    continue

        # 최종 결과 확인
        total_users = User.objects.filter(username__startswith="user").count()
        self.stdout.write(self.style.SUCCESS(f"✅ 총 {total_users:,}명의 테스트 사용자가 생성되었습니다!"))
        self.stdout.write(f"📈 이번 실행에서 {created_count:,}명의 새 사용자가 추가되었습니다.")

    def verify_users(self, expected_count: int):
        """테스트 사용자 검증"""
        self.stdout.write("🔍 테스트 사용자 검증 중...")

        total_count = User.objects.filter(username__startswith="user").count()
        self.stdout.write(f"📊 총 사용자 수: {total_count:,}명")

        # 패스워드 검증 (샘플)
        test_user = User.objects.filter(username="user0").first()
        if test_user and test_user.check_password("password"):
            self.stdout.write(self.style.SUCCESS("✅ 비밀번호 검증 성공"))
        else:
            self.stdout.write(self.style.ERROR("❌ 비밀번호 검증 실패"))

        # 샘플 사용자 표시
        sample_users = User.objects.filter(username__startswith="user")[:5]
        self.stdout.write("\n📋 생성된 사용자 샘플:")
        for user in sample_users:
            self.stdout.write(f"  - {user.username} (ID: {user.id})")

        if total_count >= expected_count:
            self.stdout.write(self.style.SUCCESS("✅ 모든 검증을 통과했습니다!"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️ 예상 사용자 수({expected_count:,})보다 적습니다({total_count:,})"))
