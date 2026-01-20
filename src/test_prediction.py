
import requests
import json
import time

def test_prediction():
    url = "http://localhost:8088/predict"
    payload = {
        "vehicle_full_name": "2024款 朗逸 1.5L 自动星空五百万版",
        "brand_series": "大众-朗逸",
        "years": 0.5,
        "grade": "优",
        "city": "达州",
        "mileage": 2.5,
        "new_price": 13.09
    }
    
    print(f"Sending request to {url}...")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            print("\nPrediction Success!")
            print(f"Predicted Price: {result.get('predicted_price')}")
            
            debug_info = result.get('debug', {})
            similar_vehicles = debug_info.get('similar_vehicles', [])
            
            print(f"\nFound {len(similar_vehicles)} similar vehicles.")
            
            cheyipai_count = 0
            youliang_count = 0
            
            for v in similar_vehicles:
                source = v.get('source', 'unknown')
                if source == '车易拍':
                    cheyipai_count += 1
                    print(f"Found Cheyipai record: {v['vehicle_full_name']} - Price: {v['used_price']}")
                elif source == '有辆' or source == 'unknown': # assuming unknown might be old data
                    youliang_count += 1
            
            print(f"\nSummary:")
            print(f"车易拍 records: {cheyipai_count}")
            print(f"有辆/Original records: {youliang_count}")
            
            if cheyipai_count > 0:
                print("\nSUCCESS: Detected '车易拍' data in similar vehicles!")
            else:
                print("\nWARNING: No '车易拍' data detected in similar vehicles.")
                
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("Connection failed. Server might be starting up.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Wait loop
    for i in range(10):
        try:
            requests.get("http://localhost:8088/docs", timeout=1)
            print("Server is up!")
            break
        except:
            print(f"Waiting for server... ({i+1}/10)")
            time.sleep(5)
            
    test_prediction()
