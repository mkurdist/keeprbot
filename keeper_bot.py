import time
import os
import json
import logging
from web3 import Web3
from flask import Flask, jsonify

# تنظیمات لاگر
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# خواندن متغیرهای محیطی از Render
RPC_URL = os.getenv("GENLAYER_RPC_URL", "https://studio.genlayer.com/rpc")
KEEPER_PRIVATE_KEY = os.getenv("KEEPER_PRIVATE_KEY")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")
GRACE_PERIOD = 86400  # ۲۴ ساعت

if not KEEPER_PRIVATE_KEY or not CONTRACT_ADDRESS:
    logger.error("CRITICAL ERROR: KEEPER_PRIVATE_KEY or CONTRACT_ADDRESS is missing!")

# اتصال به بلاکچین
w3 = Web3(Web3.HTTPProvider(RPC_URL))
keeper_account = w3.eth.account.from_key(KEEPER_PRIVATE_KEY) if KEEPER_PRIVATE_KEY else None

CONTRACT_ABI = json.loads('''[
    {"name": "get_case_state", "type": "function", "inputs": [{"name": "case_id", "type": "string"}], "outputs": [{"type": "string"}]},
    {"name": "get_case", "type": "function", "inputs": [{"name": "case_id", "type": "string"}], "outputs": [{"type": "string"}]},
    {"name": "force_finalize", "type": "function", "inputs": [{"name": "case_id", "type": "string"}]}
]''')

contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI) if CONTRACT_ADDRESS else None

def process_case(case_id: str):
    if not contract or not keeper_account: return f"[{case_id}] Not Configured"
    try:
        state = contract.functions.get_case_state(case_id).call().strip()
        if state not in ["SUBMITTED", "ACCEPTED", "DISPUTED"]:
            return f"[{case_id}] Skipped (State: {state})"

        case_data_str = contract.functions.get_case(case_id).call()
        case_data = json.loads(case_data_str)
        deadline = int(case_data.get("deadline", 0))

        if deadline == 0:
            return f"[{case_id}] No deadline"
            
        current_time = int(time.time())
        if current_time >= (deadline + GRACE_PERIOD):
            logger.info(f"Target Acquired: Case {case_id} expired. Executing force_finalize...")
            
            tx = contract.functions.force_finalize(case_id).build_transaction({
                'from': keeper_account.address,
                'nonce': w3.eth.get_transaction_count(keeper_account.address),
                'gas': 2000000,
                'gasPrice': w3.eth.gas_price
            })
            
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=KEEPER_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            w3.eth.wait_for_transaction_receipt(tx_hash)
            
            logger.info(f"SUCCESS! Case {case_id} finalized.")
            return f"[{case_id}] Finalized! 0.5 GEN earned."
        else:
            return f"[{case_id}] Waiting for grace period"
            
    except Exception as e:
        logger.error(f"Error processing case {case_id}: {e}")
        return f"[{case_id}] Error: {str(e)}"

# صفحه اصلی برای اینکه رندر متوجه شود سرور زنده است
@app.route('/')
def home():
    return "AgentCourt Keeper Bot is Active & Listening!"

# این آدرس هر ۵ دقیقه توسط سایت خارجی صدا زده می‌شود
@app.route('/scan-network')
def scan_network():
    active_cases_to_monitor = ["AC-12345", "AC-67890"]
    logger.info("External Ping Received! Scanning cases...")
    
    results = []
    for case_id in active_cases_to_monitor:
        res = process_case(case_id)
        results.append(res)
        
    return jsonify({"status": "Scan Complete", "details": results})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
