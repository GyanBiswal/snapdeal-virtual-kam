from backend.agent.seller_agent import SellerAgent


def main():
    agent = SellerAgent()
    print("Snapdeal Virtual KAM (type 'quit' to exit, '/state' to see tracked state)\n")
    print("KAM:", agent.greeting(), "\n")
    while True:
        try:
            message = input("You: ")
        except (EOFError, KeyboardInterrupt):
            break
        if message.strip().lower() in {"quit", "exit"}:
            break
        if message.strip() == "/state":
            s = agent.state
            print(f"  covered_topics: {sorted(s.covered_topics)}")
            print(f"  seller_facts: {s.seller_facts}")
            print(f"  recommendations_given: {s.recommendations_given}")
            print(f"  agreed_actions: {s.agreed_actions}\n")
            continue
        result = agent.respond(message)
        label = "KAM:" if result.ok else f"[{result.error_type}]"
        print(f"{label} {result.text}\n")


if __name__ == "__main__":
    main()