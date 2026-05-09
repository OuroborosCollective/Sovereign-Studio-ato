import argparse

def main():
    parser = argparse.ArgumentParser(description='Social Media Agent for Beta Testers')
    parser.add_argument('--target_platform', type=str, required=True, help='Target platform (e.g., Reddit, Discord)')
    parser.add_argument('--app_link', type=str, required=True, help='Google Play App Link')
    parser.add_argument('--repo_name', type=str, required=True, help='GitHub Repository Name')

    args = parser.parse_args()

    print(f"[{args.target_platform}] Running social agent for repo: {args.repo_name}")
    print(f"[{args.target_platform}] Distributing app link: {args.app_link}")
    print(f"[{args.target_platform}] Successfully simulated tester acquisition.")

if __name__ == '__main__':
    main()
