
import requests
import json

url = "http://localhost:8087/predict"
data = {
    "vehicle_full_name": "吉利 帝豪 2017款 1.5L CVT向上互联版",
    "brand_series": "吉利-帝豪",
    "years": 8.33,
    "grade": "中",
    "city": "邢台",
    "mileage": 8.0,
    "new_price": 7.98
}

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    res_json = response.json()
    print("Response keys:", res_json.keys())
    
    if 'price_matrix' in res_json:
        print("price_matrix found.")
        print(json.dumps(res_json['price_matrix'], indent=2, ensure_ascii=False))
        if not res_json['price_matrix']:
            print("WARNING: price_matrix is empty dict!")
    else:
        print("price_matrix NOT found in response!")

    if 'identical_records' in res_json:
         print(f"Identical records count: {len(res_json['identical_records'])}")
         for r in res_json['identical_records']:
             print(f"  In range: {r.get('in_range')}, Prediction range: {r.get('prediction_range')}")

except Exception as e:
    print(f"Error: {e}")
