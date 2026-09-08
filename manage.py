#!/usr/bin/env python3
import argparse
import sys

from bookkeeping_store import (
    create_user,
    delete_user,
    init_db,
    list_users,
    set_user_disabled,
    set_user_password,
)


def print_users():
    users = list_users()
    if not users:
        print('暂无用户')
        return
    print('ID  用户名        角色   状态   账单数  创建时间')
    print('--  ----------  -----  -----  ------  -------------------')
    for user in users:
        status = '停用' if user['disabled'] else '启用'
        print(
            f"{str(user['id']).ljust(2)}  "
            f"{user['username'][:10].ljust(10)}  "
            f"{user['role'].ljust(5)}  "
            f"{status.ljust(5)}  "
            f"{str(user['loan_count']).rjust(6)}  "
            f"{user['created_at']}"
        )


def ask(prompt, default=''):
    value = input(f'{prompt} [{default}]：').strip()
    return value or default


def main():
    parser = argparse.ArgumentParser(prog='manage.py')
    sub = parser.add_subparsers(dest='cmd', required=True)

    sub.add_parser('users')

    add = sub.add_parser('add-user')
    add.add_argument('--role', default='user', choices=('admin', 'user'))
    add.add_argument('--username')
    add.add_argument('--password')

    reg = sub.add_parser('register')
    reg.add_argument('--username')
    reg.add_argument('--password')

    reset = sub.add_parser('set-password')
    reset.add_argument('username')
    reset.add_argument('--password')

    toggle = sub.add_parser('toggle-user')
    toggle.add_argument('username')

    disable = sub.add_parser('disable-user')
    disable.add_argument('username')
    disable.add_argument('--enable', action='store_true')

    delete = sub.add_parser('delete-user')
    delete.add_argument('username')

    args = parser.parse_args()
    init_db()

    if args.cmd == 'users':
        print_users()
        return 0

    if args.cmd in ('add-user', 'register'):
        username = args.username or ask('用户名', 'newuser')
        password = args.password or ask('密码')
        role = 'user' if args.cmd == 'register' else args.role
        user = create_user(username, password, role=role)
        print(f"已创建用户：{user['username']} ({user['role']})")
        return 0

    user = None
    if args.cmd in ('set-password', 'toggle-user', 'disable-user', 'delete-user'):
        from bookkeeping_store import get_user_by_username

        user = get_user_by_username(args.username)
        if not user:
            print('用户不存在', file=sys.stderr)
            return 2

    if args.cmd == 'set-password':
        password = args.password or ask('新密码')
        set_user_password(user['id'], password)
        print('密码已更新')
        return 0

    if args.cmd == 'toggle-user':
        set_user_disabled(user['id'], not bool(user['disabled']))
        print('用户状态已切换')
        return 0

    if args.cmd == 'disable-user':
        set_user_disabled(user['id'], not args.enable)
        print('用户状态已更新')
        return 0

    if args.cmd == 'delete-user':
        confirm = input(f"确定删除用户 {user['username']} 吗？输入 yes 确认：").strip().lower()
        if confirm != 'yes':
            print('已取消')
            return 1
        delete_user(user['id'])
        print('用户已删除')
        return 0

    return 2


if __name__ == '__main__':
    raise SystemExit(main())
