#!/usr/bin/env python3
"""
통합 테스트 파일의 메서드 시그니처를 자동으로 수정하는 스크립트
"""

import re
import os

def fix_test_file(file_path):
    """테스트 파일의 메서드 시그니처를 수정"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # 1. User import 추가 (이미 있는지 확인)
    if 'from django.contrib.auth.models import User' not in content:
        content = re.sub(
            r'(import pytest\nfrom django\.utils import timezone)',
            r'import pytest\nfrom django.contrib.auth.models import User\nfrom django.utils import timezone',
            content
        )

    # 2. 테스트 메서드 내에서 user 생성 추가 (각 테스트 메서드의 시작 부분)
    def add_users_to_test(match):
        method_header = match.group(0)
        # 이미 User 생성이 있는지 확인
        if 'User.objects.create' in match.group(0):
            return method_header

        # User 생성 코드 추가
        user_creation = '''        # 사용자 생성
        regular_user = User.objects.create_user(username=f"testuser_{self.__class__.__name__}_{method.__name__}", email="test@example.com")
        superuser = User.objects.create_superuser(username=f"admin_{self.__class__.__name__}_{method.__name__}", email="admin@example.com")

'''

        # 메서드의 첫 번째 주석 뒤에 user 생성 추가
        lines = method_header.split('\n')
        insert_point = 1  # 메서드 정의 라인 다음

        # 첫 번째 주석이나 설명을 찾아서 그 뒤에 삽입
        for i, line in enumerate(lines[1:], 1):
            if line.strip().startswith('"""') and line.strip().endswith('"""'):
                insert_point = i + 1
                break
            elif line.strip().startswith('#'):
                continue
            elif line.strip() and not line.strip().startswith('#'):
                insert_point = i
                break

        lines.insert(insert_point, user_creation)
        return '\n'.join(lines)

    # 테스트 메서드 패턴 매치 및 user 생성 추가
    content = re.sub(
        r'(def test_[^(]+\([^)]*\):[^}]*?"""[^"]*?"""[^}]*?)(\n        # \d+\. |\n        [A-Za-z])',
        add_users_to_test,
        content,
        flags=re.DOTALL
    )

    # 3. reserve_stock 호출 수정 (user_id 또는 metadata 파라미터 제거하고 user 추가)
    # user_id="..." 를 user=regular_user로 변경
    content = re.sub(
        r'stock_service\.reserve_stock\([^)]*user_id="[^"]*"[^)]*\)',
        lambda m: re.sub(r'user_id="[^"]*"', 'user=regular_user', m.group(0)),
        content
    )

    # metadata 파라미터 제거
    content = re.sub(
        r'(stock_service\.reserve_stock\([^)]*),\s*metadata=[^,)]+([^)]*\))',
        r'\1\2',
        content
    )

    # user 파라미터가 없는 reserve_stock 호출에 추가
    def add_user_to_reserve_stock(match):
        call = match.group(0)
        if 'user=' not in call:
            # 마지막 파라미터 뒤에 user 추가
            call = re.sub(r'\)$', ', user=regular_user)', call)
        return call

    content = re.sub(
        r'stock_service\.reserve_stock\([^)]+\)',
        add_user_to_reserve_stock,
        content
    )

    # 4. cancel_reservation 호출 수정 (user 파라미터 추가)
    def fix_cancel_reservation(match):
        call = match.group(0)
        if 'user=' not in call and ', regular_user' not in call and ', superuser' not in call:
            # reservation_id 다음에 user 추가
            call = re.sub(
                r'cancel_reservation\(([^,]+),\s*',
                r'cancel_reservation(\1, regular_user, ',
                call
            )
        return call

    content = re.sub(
        r'stock_service\.cancel_reservation\([^)]+\)',
        fix_cancel_reservation,
        content
    )

    # 5. confirm_reservation 호출 수정 (user 파라미터 추가, metadata 제거)
    def fix_confirm_reservation(match):
        call = match.group(0)
        # metadata 파라미터 제거
        call = re.sub(r',\s*metadata=[^,)]+', '', call)

        if 'user=' not in call and ', superuser' not in call:
            # reservation_id 다음에 superuser 추가
            call = re.sub(
                r'confirm_reservation\(([^,)]+)\)',
                r'confirm_reservation(\1, superuser)',
                call
            )
        return call

    content = re.sub(
        r'stock_service\.confirm_reservation\([^)]+\)',
        fix_confirm_reservation,
        content
    )

    # 6. inbound_stock 호출 수정 (user 파라미터 추가)
    def fix_inbound_stock(match):
        call = match.group(0)
        if 'user=' not in call and ', superuser' not in call:
            # 마지막 파라미터 뒤에 user 추가
            call = re.sub(r'\)$', ', user=superuser)', call)
        return call

    content = re.sub(
        r'stock_service\.inbound_stock\([^)]+\)',
        fix_inbound_stock,
        content
    )

    # 변경사항이 있으면 파일 저장
    if content != original_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"수정 완료: {file_path}")
        return True
    else:
        print(f"변경사항 없음: {file_path}")
        return False

def main():
    """메인 함수"""
    test_dir = "apps/products/tests/integration"

    if not os.path.exists(test_dir):
        print(f"디렉토리가 존재하지 않습니다: {test_dir}")
        return

    modified_files = []

    for filename in os.listdir(test_dir):
        if filename.startswith("test_") and filename.endswith(".py"):
            file_path = os.path.join(test_dir, filename)
            if fix_test_file(file_path):
                modified_files.append(file_path)

    print(f"\n총 {len(modified_files)}개 파일이 수정되었습니다:")
    for file_path in modified_files:
        print(f"  - {file_path}")

if __name__ == "__main__":
    main()