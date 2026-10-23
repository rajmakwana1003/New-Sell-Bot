import asyncio
import sys

try:
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

async def run_verification():
    print("=" * 60)
    print("RUNNING END-TO-END SYSTEM VERIFICATION")
    print("=" * 60)

    from database.db import init_db, get_db, get_next_id, get_next_ids
    print("\n1. Connecting to database & initializing...")
    await init_db()
    db = get_db()
    pong = await db.command("ping")
    assert pong.get("ok") == 1, "Ping failed"
    print("   [PASS] DB connection active & responsive.")

    # 2. Test ID generators
    print("\n2. Testing atomic ID counters...")
    id1 = await get_next_id("test_counter")
    start_id = await get_next_ids("test_counter", 5)
    print(f"   [PASS] get_next_id: {id1}, get_next_ids (5 count) start: {start_id}")
    assert start_id > id1

    # 3. Test Categories & Bulk Coupons
    print("\n3. Testing Categories & Bulk Coupons...")
    from database.requests import (
        add_category, add_coupons_bulk, 
        get_available_coupons, get_category_stock_summary, 
        get_inventory_summary, delete_category_db
    )
    cat = await add_category(db, "Test Auto Category", description="Test Description")
    print(f"   [PASS] Created test category ID: {cat.id}")

    test_codes = [f"TEST-CODE-{i}" for i in range(10)]
    inserted = await add_coupons_bulk(db, cat.id, test_codes, 99.0)
    print(f"   [PASS] Bulk inserted {inserted} coupons in 1 query.")
    assert inserted == 10

    avail = await get_available_coupons(db, cat.id)
    assert len(avail) == 10, f"Expected 10 available, got {len(avail)}"
    print(f"   [PASS] Available coupons count verified: {len(avail)}")

    stock_summary = await get_category_stock_summary(db)
    print(f"   [PASS] Stock summary retrieved ({len(stock_summary)} categories).")

    inv_summary = await get_inventory_summary(db)
    print(f"   [PASS] Optimized inventory summary retrieved ({len(inv_summary)} categories).")

    # 4. Test Transactions, Reservations & Strict UTR Checks
    print("\n4. Testing Transaction Lifecycle & UTR Checks...")
    from database.requests import (
        create_transaction, reserve_coupons_atomic, update_transaction,
        check_duplicate_utr, find_user_transaction, find_transaction_robust,
        finalize_sale, reverse_sale
    )
    test_user_id = 999999999
    tx = await create_transaction(db, user_id=test_user_id, amount=198.0, quantity=2, provider_payment_charge_id="SHN-TEST1234")
    print(f"   [PASS] Transaction created: ID={tx.id}, ChargeID={tx.provider_payment_charge_id}")

    reserved = await reserve_coupons_atomic(db, cat.id, 2, tx.id)
    assert reserved is not None and len(reserved) == 2, "Reservation failed"
    print(f"   [PASS] Atomically reserved {len(reserved)} coupons.")

    test_utr = "998877665544"
    # Verify no duplicate exists yet
    dup = await check_duplicate_utr(db, test_utr, exclude_tx_id=tx.id)
    assert dup is None, "False duplicate detected"
    print("   [PASS] Pre-submission UTR check: Clean.")

    # Submit UTR
    await update_transaction(db, tx.id, utr=test_utr, payment_proof_id=f"UTR: {test_utr} | File: test_photo")
    print("   [PASS] Transaction updated with UTR.")

    # Now verify duplicate detection catches it
    dup2 = await check_duplicate_utr(db, test_utr, exclude_tx_id=888888)
    assert dup2 is not None and dup2.id == tx.id, "Duplicate UTR check failed to catch existing UTR"
    print(f"   [PASS] Duplicate UTR correctly detected: tx_id={dup2.id}")

    # Test user transaction search
    user_tx = await find_user_transaction(db, test_user_id, "SHN-TEST1234")
    assert user_tx is not None and user_tx.id == tx.id, "find_user_transaction failed on order ID"
    user_tx_utr = await find_user_transaction(db, test_user_id, test_utr)
    assert user_tx_utr is not None and user_tx_utr.id == tx.id, "find_user_transaction failed on UTR"
    user_tx_other = await find_user_transaction(db, 111111, "SHN-TEST1234")
    assert user_tx_other is None, "find_user_transaction incorrectly matched other user"
    print("   [PASS] User transaction search isolation verified.")

    # Test find_transaction_robust (admin search)
    admin_tx = await find_transaction_robust(db, "SHN-TEST1234")
    assert admin_tx is not None and admin_tx.id == tx.id
    print("   [PASS] Admin transaction lookup verified.")

    # Test finalize sale and reverse sale
    await finalize_sale(db, tx.id, test_user_id)
    tx_completed = await find_transaction_robust(db, str(tx.id))
    assert tx_completed.status == "completed"
    print("   [PASS] Finalize sale completed.")

    await reverse_sale(db, tx.id)
    tx_reversed = await find_transaction_robust(db, str(tx.id))
    assert tx_reversed.status == "reversed"
    print("   [PASS] Reverse sale completed.")

    # 5. Test Typography & HTML Sanitization
    print("\n5. Testing Typography & HTML Escaping...")
    from utils.fonts import (
        format_coupon_code, sanitize_telegram_html
    )
    raw_code = "XYZ-1234-5678 | PIN: 9988"
    formatted = format_coupon_code(raw_code)
    assert "Code:" in formatted and "PIN:" in formatted
    print("   [PASS] Gift Card PIN splitting formatted cleanly.")

    xss_test = "<script>alert('test')</script> & <b>Safe</b>"
    cleaned = sanitize_telegram_html(xss_test)
    assert "<script>" not in cleaned and "<b>Safe</b>" in cleaned
    print("   [PASS] HTML sanitizer safely strips unsafe tags.")

    # Clean up test artifacts in DB
    print("\n6. Cleaning up test data...")
    await delete_category_db(db, cat.id)
    await db.transactions.delete_one({"_id": tx.id})
    await db.counters.delete_one({"_id": "test_counter"})
    print("   [PASS] Test data wiped cleanly.")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_verification())
