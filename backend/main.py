import json

from backend.analysis.seller_analysis import generate_report

if __name__ == "__main__":
    print(json.dumps(generate_report(), indent=2, ensure_ascii=False))