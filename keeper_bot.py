import time
import os
import json
import logging
from web3 import Web3

# تنظیمات لاگر برای دیدن لاگ‌ها در کنسول Render
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ۱. خواندن متغیرهای محیطی به صورت امن از پنل Render
RPC_URL = os.getenv("GENLAYER_RPC_URL", "https://studio.genlayer.com/rpc")
KEEPER_PRIVATE_KEY = os.getenv("KEEPER_PRIVATE_KEY")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")

GRACE_PERIOD = 86400  # ۲۴ ساعت بر حسب ثانیه

if not KEEPER_PRIVATE_KEY or not CONTRACT_ADDRESS:
    logger.error("CRITICAL ERROR: KEEPER_PRIVATE_KEY or CONTRACT_ADDRESS is missing in Environment Variables!")
    exit(1)

# ۲. اتصال به بلاکچین و ساخت شیء کیف پول
w3 = Web3(Web3.HTTPProvider(RPC_URL))
keeper_account = w3.eth.account.from_key(KEEPER_PRIVATE_KEY)

# ۳. بارگذاری ABI قرارداد
CONTRACT_ABI = json.loads('''[
    {"name": "get_case_state", "type": "function", "inputs": [{"name": "case_id", "type": "string"}], "outputs": [{"type": "string"}]},
    {"name": "get_case", "type": "function", "inputs": [{"name": "case_id", "type": "string"}], "outputs": [{"type": "string"}]},
    {"name": "force_finalize", "type": "function", "inputs": [{"name": "case_id", "type": "string"}]}
]''')

contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

def process_case(case_id: str):
    try:
        state = contract.functions.get_case_state(case_id).call().strip()
        
        if state not in ["SUBMITTED", "ACCEPTED", "DISPUTED"]:
            return  

        case_data_str = contract.functions.get_case(case_id).call()
        case_data = json.loads(case_data_str)
        deadline = int(case_data.get("deadline", 0))

        if deadline == 0:
            return
            
        current_time = int(time.time())
        
        # بررسی اتمام ددلاین و Grace Period
        if current_time >= (deadline + GRACE_PERIOD):
            logger.info(f"Target Acquired: Case {case_id} deadline passed. Executing force_finalize...")
            
            tx = contract.functions.force_finalize(case_id).build_transaction({
                'from': keeper_account.address,
                'nonce': w3.eth.get_transaction_count(keeper_account.address),
                'gas': 2000000,
                'gasPrice': w3.eth.gas_price
            })
            
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=KEEPER_PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Transaction sent! Hash: {tx_hash.hex()} | Awaiting confirmation...")
            w3.eth.wait_for_transaction_receipt(tx_hash)
            logger.info(f"SUCCESS! Case {case_id} finalized. Earned 0.5 GEN bounty.\n")
            
    except Exception as e:
        logger.error(f"Error processing case {case_id}: {e}")

def main():
    logger.info("==================================================")
    logger.info(f"AgentCourt Autonomous Keeper Bot Started!")
    logger.info(f"Monitoring network with Wallet: {keeper_account.address}")
    logger.info("==================================================")
    
    while True:
        # اینجا باید لیست کیس‌های فعال را قرار دهید. 
        # (در نسخه پیشرفته می‌توانید این لیست را از API فروشگاه یا دیتابیس بگیرید)
        active_cases_to_monitor = ["AC-12345", "AC-67890"] 
        
        logger.info(f"Scanning {len(active_cases_to_monitor)} active cases for expired deadlines...")
        for case_id in active_cases_to_monitor:
            process_case(case_id)
            
        logger.info("Scan complete. Sleeping for 1 hour...\n")
        time.sleep(3600)  # اجرای حلقه هر ۱ ساعت یک‌بار

if __name__ == "__main__":
    main()
