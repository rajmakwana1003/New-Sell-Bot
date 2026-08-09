import os
import time
import random
import string
import secrets
import re
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from motor.motor_asyncio import AsyncIOMotorDatabase
from database.db import AsyncSessionLocal
from database.requests import (
    get_or_create_user, get_categories, get_available_coupons,
    get_coupon, create_transaction, get_setting, get_user_by_id, 
    finalize_sale, update_transaction, get_coupons_by_transaction, 
    get_available_reward, use_reward, get_channels, increment_user_warning, 
    get_transaction, find_transaction_robust, get_support_contacts,
    get_category, get_category_stock_summary, get_inventory_summary,
    reserve_coupons_atomic, release_coupons_by_transaction,
    get_user_transactions_completed, get_transaction_with_items,
    count_available_rewards, get_user_redeemed_rewards, update_user,
    get_user_order_counts
)
from utils.fonts import bold_sans, sans_normal, stylize_html

# --- Typography Helpers ---
def sh(text: str) -> str:
    """Stylize Header (bold sans-serif)."""
    return stylize_html(text, bold_sans)

def sb(text: str) -> str:
    """Stylize Body (normal sans-serif)."""
    return stylize_html(text, sans_normal)

# --- Configuration & Helpers ---
payment_abuse_tracker: dict = {}
PAYMENT_WINDOW = 3600
PAYMENT_LIMIT  = 5

DEFAULT_INSTRUCTIONS = (
    "🛒 <b>How to redeem:</b>\n"
    "├─ Visit: sheinindia.in/c/sheinverse-17042026\n"
    "├─ Add items worth ₹1000+\n"
    "├─ Apply code at checkout\n"
    "└─ Record <b>UNCUT VIDEO</b> throughout\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📜 <b>Terms:</b> No refund after delivery. Video proof mandatory for replacements. ❌"
)

DEFAULT_WELCOME_TEXT = (
    sh("🚀 <b>Welcome to PREMIUM SHOP!</b> 🎟️\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n") +
    sb(
        "Hello <b>{full_name}</b>! Ready to unlock some amazing deals?\n\n"
        "We are your trusted source for <b>verified SHEIN discount vouchers</b>. "
        "Get premium codes with <b>instant delivery</b> and 24/7 protection.\n\n"
        "✨ <b>WHY CHOOSE US?</b>\n"
        "├─ ⚡ <b>Instant Delivery:</b> No waiting, get codes now.\n"
        "├─ 💰 <b>Unbeatable Prices:</b> Best rates in the market.\n"
        "├─ ✅ <b>100% Verified:</b> All vouchers are pre-checked.\n"
        "└─ 📞 <b>24/7 Support:</b> Real human help 1-on-1.\n\n"
        "🛍️ <b>WHAT YOU CAN DO:</b>\n"
        "🛒 <b>Browse:</b> Check the latest available coupons.\n"
        "💳 <b>Buy:</b> Purchase instantly using secure UPI.\n"
        "📦 <b>Orders:</b> View your purchased vouchers.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚨 <b>MANDATORY RULE:</b>\n"
        "You <u>MUST</u> record an <b>uncut screen recording</b> from the moment you pay until you apply the code. "
        "No video = No replacement. No exceptions! ❌\n\n"
        "👇 <b>Select an option below to begin:</b>"
    )
)

def generate_order_id():
    return "SHN-" + secrets.token_hex(4).upper()

# Stylized Button Names for visual excellence
BTN_BUY_COUPONS = f"🛒 {bold_sans('Buy Coupons')}"
BTN_LIVE_INVENTORY = f"📊 {bold_sans('Live Inventory')}"
BTN_MY_ORDERS = f"🛍️ {bold_sans('My Orders')}"
BTN_MY_PROFILE = f"👤 {bold_sans('My Profile')}"
BTN_REFER_EARN = f"🤝 {bold_sans('Refer & Earn')}"
BTN_HELP_SUPPORT = f"🆘 {bold_sans('Help & Support')}"
BTN_RECOVER_VOUCHER = f"🔄 {bold_sans('Recover Voucher')}"
BTN_JOIN_CHANNEL = f"📢 {bold_sans('Join Channel')}"
BTN_ADMIN_PANEL = f"🔐 {bold_sans('Admin Control Panel')}"

MENU_BUTTONS = [
    BTN_BUY_COUPONS, BTN_LIVE_INVENTORY,
    BTN_MY_ORDERS, BTN_MY_PROFILE,
    BTN_REFER_EARN, BTN_HELP_SUPPORT,
    BTN_RECOVER_VOUCHER, BTN_JOIN_CHANNEL,
    BTN_ADMIN_PANEL
]

router = Router()

# ── Application-level caches (avoid repeated DB hits on rapid taps) ──────────
_CAT_CACHE: dict = {"data": None, "expires": 0}
_INV_CACHE: dict = {"data": None, "expires": 0}

class UserStates(StatesGroup):
    reading_terms = State()
    selecting_quantity = State()
    confirming_order = State()
    waiting_for_payment_screenshot = State()
    waiting_for_utr = State()
    recover_order_id = State()

@router.callback_query(F.data.startswith("paid_"))
async def paid_button_handler(callback: CallbackQuery, state: FSMContext):
    tx_id = int(callback.data.split("_")[-1])
    await state.update_data(tx_id=tx_id)
    await state.set_state(UserStates.waiting_for_payment_screenshot)
    
    header = sh("📸 <b>UPLOAD SCREENSHOT</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n")
    body = sb("Please upload your <b>Payment Screenshot</b> now.\n\n<i>Note: Once received, I will ask for your UTR number!</i>")
    await callback.message.answer(header + body)
    await callback.answer()

def main_reply_keyboard(user_id: int, is_admin: bool = False):
    keyboard = [
        [KeyboardButton(text=BTN_BUY_COUPONS), KeyboardButton(text=BTN_LIVE_INVENTORY)],
        [KeyboardButton(text=BTN_MY_ORDERS), KeyboardButton(text=BTN_MY_PROFILE)],
        [KeyboardButton(text=BTN_REFER_EARN), KeyboardButton(text=BTN_HELP_SUPPORT)],
        [KeyboardButton(text=BTN_RECOVER_VOUCHER), KeyboardButton(text=BTN_JOIN_CHANNEL)],
    ]
    super_admins = [int(id.strip()) for id in os.getenv("ADMIN_ID", "0").split(",") if id.strip()]
    if user_id in super_admins or is_admin:
        keyboard.append([KeyboardButton(text=BTN_ADMIN_PANEL)])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, input_field_placeholder=bold_sans("How can we help you today?"))

# --- Core Handlers ---

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear()
    referred_by = None
    if command.args:
        try: referred_by = int(command.args)
        except ValueError: pass

    from middlewares.checks import USER_CACHE
    _cached = USER_CACHE.get(message.from_user.id)
    if _cached and not referred_by:
        is_admin = _cached["is_admin"]
        asyncio.create_task(_update_user_bg(
            message.from_user.id,
            message.from_user.username,
            message.from_user.full_name,
        ))
    else:
        user, created = await get_or_create_user(
            session, message.from_user.id,
            message.from_user.username,
            message.from_user.full_name,
            referred_by=referred_by,
        )
        is_admin = user.is_admin
        
        is_new_user = created or (_cached.get("is_new") if _cached else False)
        if is_new_user and referred_by and referred_by != message.from_user.id:
            if _cached: _cached["is_new"] = False
            try:
                ref_text = sh("🎊 <b>New Referral!</b>\n\n") + sb(f"<b>{message.from_user.full_name}</b> joined using your link. Keep going! 🚀")
                await message.bot.send_message(
                    chat_id=referred_by,
                    text=ref_text
                )
            except Exception:
                pass

    current = await get_setting(session, "welcome_message", DEFAULT_WELCOME_TEXT)
    welcome_text = current.replace("{full_name}", message.from_user.full_name)
    await message.answer(welcome_text, reply_markup=main_reply_keyboard(message.from_user.id, is_admin))


async def _update_user_bg(user_id: int, username: str, full_name: str):
    try:
        from database.db import AsyncSessionLocal as _ASL
        async with _ASL() as _s:
            await _s.users.update_one(
                {"_id": user_id},
                {"$set": {"username": username, "full_name": full_name}}
            )
    except Exception:
        pass

@router.message(F.text == BTN_ADMIN_PANEL)
async def user_admin_btn(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear()
    super_admins = [int(id.strip()) for id in os.getenv("ADMIN_ID", "0").split(",") if id.strip()]
    user = await get_user_by_id(session, message.from_user.id)
    is_admin = user.is_admin if user else False
    if message.from_user.id in super_admins or is_admin:
        from handlers.admin import cmd_admin
        await cmd_admin(message, state, session)

@router.callback_query(F.data == "check_join")
async def check_join_callback(callback: CallbackQuery, bot: Bot, session: AsyncIOMotorDatabase):
    channels = await get_channels(session)
    not_joined = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch.chat_id, user_id=callback.from_user.id)
            if member.status not in ["member", "administrator", "creator"]: not_joined.append(ch)
        except: continue
    if not_joined:
        await callback.answer(bold_sans("⚠️ Please join all channels first!"), show_alert=True)
        return
    access_msg = sh("✅ <b>Access Granted!</b>\n\n") + sb("You are now authorized to use the bot.")
    await callback.message.answer(access_msg, reply_markup=main_reply_keyboard(callback.from_user.id))
    await callback.message.delete(); await callback.answer()

@router.message(F.text == BTN_BUY_COUPONS)
async def user_browse(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear()
    now = time.time()
    if now < _CAT_CACHE["expires"] and _CAT_CACHE["data"] is not None:
        cat_stats = _CAT_CACHE["data"]
    else:
        cat_stats = await get_category_stock_summary(session)
        _CAT_CACHE["data"]    = cat_stats
        _CAT_CACHE["expires"] = now + 5
        
    if not cat_stats:
        closed_msg = sh("🛒 <b>Store Temporarily Closed</b>\n\n") + sb("We are currently restocking our digital inventory. Check back in 5-10 minutes! 🔄")
        await message.answer(closed_msg)
        return
        
    keyboard = []
    for cat, stock, price in cat_stats:
        if stock > 0: 
            keyboard.append([InlineKeyboardButton(text=f"🎫 {bold_sans(cat.name)} — {bold_sans('₹' + str(price))}", callback_data=f"agree_terms_{cat.id}")])
        else: 
            keyboard.append([InlineKeyboardButton(text=f"❌ {bold_sans(cat.name)} — {bold_sans('Out of Stock')}", callback_data="sold_out_alert")])
        
    msg_text = sh("🛒 <b>SELECT YOUR PACKAGE</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n") + sb("All codes are pre-verified and valid for the current month. Choose your desired discount below:")
    await message.answer(msg_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data == "sold_out_alert")
async def sold_out_alert_cb(callback: CallbackQuery):
    await callback.answer(bold_sans("🔴 This item is currently sold out. Restocking soon!"), show_alert=True)

@router.callback_query(F.data == "back_to_cats")
async def back_to_cats_cb(callback: CallbackQuery, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear(); await user_browse(callback.message, state, session); await callback.message.delete(); await callback.answer()

@router.callback_query(F.data.startswith("agree_terms_"))
async def show_category_terms(callback: CallbackQuery, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear() 
    cat_id = int(callback.data.split("_")[-1])
    cat = await get_category(session, cat_id)
    if not cat: return await callback.answer("Error.")
    default_terms = (
        sh("📜 <b>READ BEFORE BUYING</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n") +
        sb(
            "1️⃣ <b>VIDEO PROOF:</b> Start screen recording <u>NOW</u> (before payment).\n\n"
            "2️⃣ <b>REDEEM NOW:</b> Vouchers must be used immediately after receiving.\n\n"
            "3️⃣ <b>SUPPORT:</b> No replacement without full uncut video proof.\n\n"
            "4️⃣ <b>REQUISITES:</b> Your SHEIN cart must be <b>₹1000+</b>.\n\n"
            "✅ <i>Do you agree to follow these rules?</i>"
        )
    )
    await state.update_data(selected_cat_id=cat_id)
    await state.set_state(UserStates.reading_terms)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=bold_sans("✅ Yes, I Understand"), callback_data=f"buy_cat_{cat_id}")], 
        [InlineKeyboardButton(text=bold_sans("🔙 Back"), callback_data="back_to_cats")]
    ])
    
    terms_text = stylize_html(cat.terms, sans_normal) if cat.terms else default_terms
    await callback.message.edit_text(terms_text, reply_markup=kb, disable_web_page_preview=True)
    await callback.answer()

@router.callback_query(F.data.startswith("buy_cat_"), UserStates.reading_terms)
async def start_buy_flow(callback: CallbackQuery, state: FSMContext, session: AsyncIOMotorDatabase):
    cat_id = int(callback.data.split("_")[-1])
    available = await get_available_coupons(session, cat_id)
    if not available: return await callback.answer(bold_sans("❌ Sold out!"), show_alert=True)
    price = available[0].price_inr; cat = await get_category(session, cat_id); cat_name = cat.name
    await state.update_data(cat_id=cat_id, cat_name=cat_name, unit_price=float(price), max_stock=len(available))
    await state.set_state(UserStates.selecting_quantity)
    
    kb = [
        [InlineKeyboardButton(text=bold_sans(f"🛒 Buy {s}"), callback_data=f"qty_set_{s}") for s in [1, 2, 5] if s <= len(available)], 
        [InlineKeyboardButton(text=bold_sans("⌨️ Custom Qty"), callback_data="qty_custom")], 
        [InlineKeyboardButton(text=bold_sans("🔙 Back"), callback_data=f"agree_terms_{cat_id}")]
    ]
    
    qty_msg = sh("🔢 <b>SELECT QUANTITY</b>\n\n") + sb(f"📂 Item: <b>{cat_name}</b>\n💰 Price: <b>₹{price} each</b>\n📦 Available: <b>{len(available)}</b>\n\n<i>How many codes would you like to purchase?</i>")
    await callback.message.edit_text(qty_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("qty_set_"), UserStates.selecting_quantity)
async def process_qty_preset(callback: CallbackQuery, state: FSMContext, session: AsyncIOMotorDatabase):
    await show_order_confirmation(callback.message, state, int(callback.data.split("_")[-1])); await callback.answer()

@router.callback_query(F.data == "qty_custom", UserStates.selecting_quantity)
async def process_qty_custom_trigger(callback: CallbackQuery):
    await callback.message.answer(sh("⌨️ <b>Send the number of coupons you want:</b>")); await callback.answer()

@router.message(UserStates.selecting_quantity)
async def process_custom_quantity(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    if message.text in MENU_BUTTONS: await state.clear(); return 
    data = await state.get_data()
    try:
        qty = int(message.text)
        if qty < 1 or qty > data['max_stock']: raise ValueError
    except: 
        err_msg = sh("❌ ") + sb(f"Enter a valid quantity (1-{data['max_stock']}):")
        return await message.answer(err_msg)
    await show_order_confirmation(message, state, qty)

async def show_order_confirmation(msg_obj: Message, state: FSMContext, qty: int):
    data = await state.get_data(); total_price = qty * data['unit_price']
    await state.update_data(quantity=qty, total_price=total_price)
    await state.set_state(UserStates.confirming_order)
    summary = (
        sh("🛒 <b>ORDER SUMMARY</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n") +
        sb(
            f"📦 <b>Voucher:</b> {data['cat_name']}\n"
            f"🔢 <b>Quantity:</b> {qty} code(s)\n"
            f"💸 <b>Rate:</b> ₹{data['unit_price']}\n"
            f"💰 <b>Total Amount:</b> <b>₹{total_price}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ <i>Ready to pay and receive your codes?</i>"
        )
    )
    kb = [
        [InlineKeyboardButton(text=bold_sans(f"💳 Pay ₹{total_price} Now"), callback_data="confirm_order")], 
        [InlineKeyboardButton(text=bold_sans("❌ Cancel"), callback_data="cancel_order")]
    ]
    if msg_obj.text: await msg_obj.answer(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else: await msg_obj.edit_text(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

PAYMENT_IMAGE_CACHE = {"file_id": None}

@router.callback_query(F.data == "confirm_order", UserStates.confirming_order)
async def confirm_payment_step(callback: CallbackQuery, state: FSMContext, bot: Bot, session: AsyncIOMotorDatabase):
    data = await state.get_data(); user_id = callback.from_user.id
    if data.get("_processing"): return await callback.answer(bold_sans("⏳ Processing your order..."), show_alert=True)
    
    await callback.answer(bold_sans("⚡ Securing your stock..."))
    await state.update_data(_processing=True)

    try:
        order_id = generate_order_id()
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        
        tx = await create_transaction(
            session, user_id=user_id, 
            amount=data['total_price'], 
            quantity=data['quantity'], 
            provider_payment_charge_id=order_id,
            expires_at=expires_at
        )
        tx_id = tx.id

        coupons = await reserve_coupons_atomic(session, data['cat_id'], data['quantity'], tx_id)

        if not coupons:
            await update_transaction(session, tx_id, status='failed')
            await state.update_data(_processing=False)
            low_stock_msg = sh("❌ <b>Low Stock!</b> ") + sb("Someone else just bought these. Please try a smaller quantity.")
            return await callback.message.answer(low_stock_msg)

    except Exception as e:
        await state.update_data(_processing=False)
        print(f"Checkout Error: {e}")
        busy_msg = sh("❌ <b>Server Busy.</b> ") + sb("Please try again in 5 seconds.")
        return await callback.message.answer(busy_msg)

    upi_id = await get_setting(session, "upi_id", "wineeex42@ptyes")
    pay_msg = (
        sh("💳 <b>PAYMENT INSTRUCTIONS</b>\n━━━━━━━━━━━━━━━━━━━━━━━━\n") +
        sb(
            f"🆔 <b>Order ID:</b> <code>{order_id}</code>\n"
            f"💰 <b>Amount:</b> <b>₹{data['total_price']}</b>\n"
            f"🔗 <b>UPI:</b> <code>{upi_id}</code>\n"
            f"⏳ <b>Expires in:</b> 10 Minutes\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"1️⃣ Pay the <u>EXACT</u> amount to the UPI ID.\n"
            f"2️⃣ Save the screenshot and note the <b>12-digit UTR/Ref Number</b>.\n"
            f"3️⃣ <b>RECORD YOUR SCREEN:</b> No replacement without full uncut video proof!\n\n"
            f"👇 <b>Once paid, click the button below:</b>"
        )
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=bold_sans("✅ I Have Paid"), callback_data=f"paid_{tx_id}")],
        [InlineKeyboardButton(text=bold_sans("❌ Cancel Order"), callback_data=f"cancel_order_tx_{tx_id}")]
    ])

    try:
        # Load category custom QR if set
        cat = await get_category(session, data['cat_id'])
        qr_photo = cat.qr_file_id if (cat and cat.qr_file_id) else None

        if qr_photo:
            sent_msg = await bot.send_photo(chat_id=user_id, photo=qr_photo, caption=pay_msg, reply_markup=kb)
        elif PAYMENT_IMAGE_CACHE["file_id"]:
            sent_msg = await bot.send_photo(chat_id=user_id, photo=PAYMENT_IMAGE_CACHE["file_id"], caption=pay_msg, reply_markup=kb)
        else:
            qr_path = os.getenv("PAYMENT_METHOD_IMAGE_PATH", "assets/payment.jpg")
            if os.path.exists(qr_path):
                photo = FSInputFile(qr_path)
                sent_msg = await bot.send_photo(chat_id=user_id, photo=photo, caption=pay_msg, reply_markup=kb)
                PAYMENT_IMAGE_CACHE["file_id"] = sent_msg.photo[-1].file_id
            else:
                await bot.send_message(chat_id=user_id, text=pay_msg, reply_markup=kb)
        
        await state.update_data(tx_id=tx_id, order_id=order_id, _processing=False)
        await state.set_state(UserStates.waiting_for_payment_screenshot)
        await callback.message.delete()
    except Exception as e:
        await state.update_data(_processing=False)
        await bot.send_message(chat_id=user_id, text=pay_msg, reply_markup=kb)

@router.callback_query(F.data.startswith("cancel_order_tx_"))
async def cancel_order_tx_btn(callback: CallbackQuery, state: FSMContext, session: AsyncIOMotorDatabase):
    tx_id = int(callback.data.split("_")[-1]); user_id = callback.from_user.id
    tx = await get_transaction(session, tx_id)
    if tx and tx.user_id == user_id and tx.status == 'pending':
        await update_transaction(session, tx_id, status='cancelled')
        await release_coupons_by_transaction(session, tx_id)
    await state.clear()
    msg_text = sh("❌ <b>Order Cancelled.</b> ") + sb("Stock has been released. You can try again anytime.")
    if callback.message.photo: await callback.message.edit_caption(caption=msg_text)
    else: await callback.message.edit_text(msg_text)
    await callback.answer(bold_sans("Cancelled."))

@router.callback_query(F.data == "cancel_order")
async def cancel_order_btn(callback: CallbackQuery, state: FSMContext):
    abort_msg = sh("❌ <b>Session Aborted.</b>")
    await state.clear(); await callback.message.answer(abort_msg, reply_markup=main_reply_keyboard(callback.from_user.id))
    await callback.message.delete(); await callback.answer()

@router.message(UserStates.waiting_for_payment_screenshot, F.photo)
async def process_screenshot(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    photo_id = message.photo[-1].file_id
    await state.update_data(photo_id=photo_id)
    data = await state.get_data()
    tx_id = data.get('tx_id')
    if tx_id:
        await update_transaction(session, int(tx_id), payment_proof_id=f"FILE:{photo_id}")
    
    await state.set_state(UserStates.waiting_for_utr)
    sc_msg = (
        sh("📸 <b>SCREENSHOT RECEIVED!</b> ✅\n━━━━━━━━━━━━━━━━━━━━━━\n") +
        sb(
            f"📋 <b>Order ID:</b> <code>{data.get('order_id')}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>FINAL STEP:</b> Please send your <b>12-digit UTR Number</b>.\n\n"
            f"📍 <i>Example: 312345678901</i>"
        )
    )
    await message.answer(sc_msg)

@router.message(UserStates.waiting_for_payment_screenshot)
async def process_screenshot_invalid(message: Message):
    if message.text in MENU_BUTTONS: return
    invalid_msg = sh("⚠️ <b>Invalid Input!</b> ") + sb("Please send the <b>Payment Screenshot</b> (as a photo) to proceed.")
    await message.answer(invalid_msg)

@router.message(UserStates.waiting_for_utr, F.text)
async def process_utr_final(message: Message, state: FSMContext, bot: Bot, session: AsyncIOMotorDatabase):
    if message.text in MENU_BUTTONS: await state.clear(); return
    user_id = message.from_user.id
    
    # Robust UTR Extraction
    utr_match = re.search(r'\d{12}', message.text)
    if not utr_match:
        invalid_utr_msg = sh("⚠️ <b>INVALID UTR</b>\n") + sb("Please send the <b>12-digit UTR/Reference number</b> from your payment app.")
        return await message.answer(invalid_utr_msg)
    
    utr = utr_match.group(0)

    # Check for Duplicate UTR
    existing_utr = await find_transaction_robust(session, utr)
    if existing_utr:
        count = await increment_user_warning(session, user_id)
        if count >= 5:
            await state.clear()
            from middlewares.checks import USER_CACHE
            USER_CACHE.pop(user_id, None)
            ban_msg = sh("🚫 <b>PERMANENT BAN</b>\n\n") + sb("Reason: Multiple duplicate payment references (UTR) detected.")
            return await message.answer(ban_msg)
        dup_utr_msg = (
            sh("⚠️ <b>DUPLICATE UTR DETECTED</b>\n\n") +
            sb(
                f"This UTR (<code>{utr}</code>) has already been used for another order. Attempt logged ({count}/5 strikes).\n\n"
                f"<i>Do not reuse UTRs from old payments. Repeat offenses lead to a permanent ban!</i>"
            )
        )
        return await message.answer(dup_utr_msg)

    now_ts = time.time(); tracker = payment_abuse_tracker.setdefault(user_id, [])
    payment_abuse_tracker[user_id] = [t for t in tracker if now_ts - t < PAYMENT_WINDOW]; payment_abuse_tracker[user_id].append(now_ts)
    
    if len(payment_abuse_tracker[user_id]) >= PAYMENT_LIMIT:
        await update_user(session, user_id, is_blocked=True, is_suspicious=True, warning_count=PAYMENT_LIMIT)
        await state.clear()
        from middlewares.checks import USER_CACHE
        USER_CACHE.pop(user_id, None)
        abuse_ban_msg = sh("🚫 <b>PERMANENT BAN</b>\n\n") + sb("Reason: Suspicious payment attempts detected. Contact support for appeal.")
        return await message.answer(abuse_ban_msg)

    data = await state.get_data(); order_id = data.get('order_id'); tx_id = data.get('tx_id'); photo_id = data.get('photo_id')
    
    if tx_id:
        tx = await get_transaction(session, int(tx_id))
        if not tx or tx.status != 'pending': 
            closed_window_msg = sh("❌ ") + sb("This order window has closed.")
            return await message.answer(closed_window_msg)
        
        if not photo_id and tx.payment_proof_id and tx.payment_proof_id.startswith("FILE:"):
            photo_id = tx.payment_proof_id.split(":", 1)[1]

        if not photo_id:
            await state.set_state(UserStates.waiting_for_payment_screenshot)
            session_err_msg = sh("❌ <b>Session error.</b> ") + sb("Please re-upload your screenshot first.")
            return await message.answer(session_err_msg)

        await update_transaction(session, int(tx_id), utr=utr, payment_proof_id=f"UTR: {utr} | File: {photo_id}")
    else: 
        session_fail_msg = sh("❌ ") + sb("Session Error. Please try again.")
        return await message.answer(session_fail_msg)

    admin_id_raw = os.getenv("ADMIN_ID", "")
    primary_admin = admin_id_raw.split(",")[0].strip() if admin_id_raw else None
    
    if primary_admin:
        kb = [[InlineKeyboardButton(text=bold_sans("✅ Approve"), callback_data=f"admin_approve_{tx_id}"), 
               InlineKeyboardButton(text=bold_sans("❌ Reject"), callback_data=f"admin_reject_{tx_id}")]]
        try:
            admin_msg = (
                sh("🔔 <b>NEW PENDING ORDER</b>\n━━━━━━━━━━━━━━━━━━\n") +
                sb(
                    f"👤 <b>Client:</b> {message.from_user.full_name}\n"
                    f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                    f"📦 <b>Item:</b> {data.get('quantity', tx.quantity)} × {data.get('cat_name', '(Voucher)')}\n"
                    f"💸 <b>Paid:</b> ₹{data.get('total_price', tx.amount)}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📋 <b>ID:</b> <code>{order_id}</code>\n"
                    f"🔑 <b>UTR:</b> <code>{utr}</code>"
                )
            )
            await bot.send_photo(chat_id=primary_admin, photo=photo_id, caption=admin_msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        except Exception as e:
            print(f"Admin Notification Error: {e}")
            
    await state.clear()
    submitted_msg = (
        sh("✅ <b>ORDER SUBMITTED!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n") +
        sb(
            f"📋 <b>Order ID:</b> <code>{order_id}</code>\n"
            f"💰 <b>Total Paid:</b> ₹{data.get('total_price', tx.amount)}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ <b>STATUS:</b> Verifying Payment...\n\n"
            f"🚀 <i>Vouchers will be delivered here within 5-15 minutes. Start your screen recording now!</i>"
        )
    )
    await message.answer(submitted_msg)

@router.message(UserStates.waiting_for_utr)
async def process_utr_invalid(message: Message):
    if message.text in MENU_BUTTONS: return
    invalid_utr_err = sh("⚠️ <b>Invalid Input!</b> ") + sb("Please send your <b>12-digit UTR Number</b> (digits only).")
    await message.answer(invalid_utr_err)

@router.message(F.text == BTN_LIVE_INVENTORY)
async def user_stocks(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear()
    now = time.time()
    if now < _INV_CACHE["expires"] and _INV_CACHE["data"] is not None:
        cat_stats = _INV_CACHE["data"]
    else:
        cat_stats = await get_inventory_summary(session)
        _INV_CACHE["data"]    = cat_stats
        _INV_CACHE["expires"] = now + 5
    
    if not cat_stats:
        empty_stock_msg = sh("📊 <b>Stock Status</b>\n\n") + sb("No active registries found.")
        return await message.answer(empty_stock_msg)
        
    text = sh("📊 <b>REAL-TIME INVENTORY</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n")
    total_avail = 0
    
    for row in cat_stats:
        cat_id, cat_name, is_active, avail, pend, price = row
        status_icon = "🟢" if is_active and avail > 0 else "🟡" if is_active else "🚨"
        text += f"{status_icon} <b>{cat_name.upper()}</b>"
        if price: text += f" — <b>₹{price}</b>"
        text += sb(f"\n├─ 📦 Available: <code>{avail}</code> units\n├─ ⏳ Processing: <code>{pend}</code> units\n└─ 🛡 Status: <i>{'OPERATIONAL' if is_active else 'MAINTENANCE'}</i>\n\n")
        total_avail += avail
        
    text += sh("━━━━━━━━━━━━━━━━━━━━━━\n")
    text += sb(
        f"💎 <b>Total Vouchers:</b> <code>{total_avail}</code> units\n"
        f"🕒 <b>Last Sync:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"<i>💡 Stock data is live. Reserved units auto-release in 10 mins.</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=bold_sans("🔄 Refresh Stock"), callback_data="refresh_inventory")]])
    await message.answer(text, reply_markup=kb)

@router.callback_query(F.data == "refresh_inventory")
async def refresh_inventory_cb(callback: CallbackQuery, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear()
    now = time.time()
    _INV_CACHE["expires"] = 0
    cat_stats = await get_inventory_summary(session)
    _INV_CACHE["data"]    = cat_stats
    _INV_CACHE["expires"] = now + 5
    
    if not cat_stats:
        empty_stock_msg = sh("📊 <b>Stock Status</b>\n\n") + sb("No active registries found.")
        return await callback.message.edit_text(empty_stock_msg)
        
    text = sh("📊 <b>REAL-TIME INVENTORY</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n")
    total_avail = 0
    
    for row in cat_stats:
        cat_id, cat_name, is_active, avail, pend, price = row
        status_icon = "🟢" if is_active and avail > 0 else "🟡" if is_active else "🚨"
        text += f"{status_icon} <b>{cat_name.upper()}</b>"
        if price: text += f" — <b>₹{price}</b>"
        text += sb(f"\n├─ 📦 Available: <code>{avail}</code> units\n├─ ⏳ Processing: <code>{pend}</code> units\n└─ 🛡 Status: <i>{'OPERATIONAL' if is_active else 'MAINTENANCE'}</i>\n\n")
        total_avail += avail
        
    text += sh("━━━━━━━━━━━━━━━━━━━━━━\n")
    text += sb(
        f"💎 <b>Total Vouchers:</b> <code>{total_avail}</code> units\n"
        f"🕒 <b>Last Sync:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"<i>💡 Stock data is live. Reserved units auto-release in 10 mins.</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=bold_sans("🔄 Refresh Stock"), callback_data="refresh_inventory")]])
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except:
        pass
    await callback.answer(bold_sans("Inventory Refreshed!"))

async def show_user_orders(session: AsyncIOMotorDatabase, user_id: int, message_or_callback):
    txs = await get_user_transactions_completed(session, user_id)
    
    if not txs:
        text = (
            sh("🛍️ <b>PURCHASE LOGS</b>\n\n") +
            sb(
                "You haven't made any successful purchases yet.\n\n"
                "🚀 <b>Tip:</b> Tap 'Buy Coupons' to grab your first deal!"
            )
        )
        if isinstance(message_or_callback, Message): await message_or_callback.answer(text)
        else: await message_or_callback.message.edit_text(text)
        return
    
    text = (
        sh("🛍️ <b>ORDER HISTORY</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n") +
        sb(
            f"You have <b>{len(txs)}</b> completed orders.\n"
            f"Tap an order below to view your voucher codes:"
        )
    )
    
    keyboard = [[InlineKeyboardButton(text=f"📅 {tx.created_at.strftime('%d %b')} │ {bold_sans('₹' + str(tx.amount))} │ ID: {tx.provider_payment_charge_id[-8:] if tx.provider_payment_charge_id else f'TX-{tx.id}'}", callback_data=f"view_order_{tx.id}")] for tx in txs[:15]]
    
    if isinstance(message_or_callback, Message): await message_or_callback.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    else: await message_or_callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.message(F.text == BTN_MY_ORDERS)
async def user_orders(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear(); await show_user_orders(session, message.from_user.id, message)

@router.callback_query(F.data.startswith("view_order_"))
async def view_order_details_cb(callback: CallbackQuery, session: AsyncIOMotorDatabase):
    tx_id = int(callback.data.split("_")[-1])
    tx, items = await get_transaction_with_items(session, tx_id)
    if not tx or tx.user_id != callback.from_user.id: return await callback.answer(bold_sans("❌ Order not found."), show_alert=True)
    
    text = (
        sh("📋 <b>ORDER DETAILS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n") +
        sb(
            f"🧾 <b>Order ID:</b> <code>{tx.provider_payment_charge_id}</code>\n"
            f"📅 <b>Date:</b> {tx.created_at.strftime('%d %b %Y, %H:%M')}\n"
            f"💸 <b>Amount:</b> ₹{tx.amount}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 <b>YOUR VOUCHERS:</b>\n"
        )
    )
    for c, cat in items: text += f"▪️ {sans_normal(cat.name)}: <code>{c.code}</code>\n"
    text += sh("\n━━━━━━━━━━━━━━━━━━━━━━\n") + sb("🚀 <b>HOW TO USE:</b>\nVisit SHEIN, apply code at checkout. Remember to record your <b>uncut video</b> for safety!")
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=bold_sans("🔙 Back to History"), callback_data="back_to_history")]])); await callback.answer()

@router.callback_query(F.data == "back_to_history")
async def back_to_history_cb(callback: CallbackQuery, state: FSMContext, session: AsyncIOMotorDatabase):
    await show_user_orders(session, callback.from_user.id, callback); await callback.answer()

@router.message(F.text == BTN_REFER_EARN)
async def refer_earn(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear()
    await show_referral_menu(message, session, message.from_user.id)

async def show_referral_menu(message: Message, session: AsyncIOMotorDatabase, user_id: int):
    user = await get_user_by_id(session, user_id); status = await get_setting(session, "refer_earn_status", "on"); goal = int(await get_setting(session, "refer_goal", "3"))
    pool = await count_available_rewards(session)
    if status == "off": 
        offline_msg = sh("👥 <b>REFERRAL SYSTEM</b>\n\n") + sb("The program is currently offline. 🔄")
        return await message.answer(offline_msg)
    
    progress = user.referral_count if user else 0
    bar_size = 10
    filled = min(int((progress / goal) * bar_size), bar_size) if goal > 0 else 0
    bar = "🟩" * filled + "⬜" * (bar_size - filled)
    
    kb = [
        [InlineKeyboardButton(text=bold_sans(f"🎁 Claim Reward {'✅' if progress >= goal else ''}"), callback_data="redeem_referral")],
        [InlineKeyboardButton(text=bold_sans("🔗 Get Invite Link"), callback_data="view_referral_link"), InlineKeyboardButton(text=bold_sans("📜 Rules"), callback_data="view_refer_rules")],
        [InlineKeyboardButton(text=bold_sans("🏆 Top Leaders"), callback_data="view_leaderboard"), InlineKeyboardButton(text=bold_sans("🎟️ My Rewards"), callback_data="my_redeemed_rewards")]
    ]
    
    text = (
        sh("👥 <b>REFER & EARN PROGRAM</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n") +
        sb(
            f"Invite your friends and earn premium vouchers for <b>FREE</b>! 🎁\n\n"
            f"🎯 <b>Goal:</b> {goal} Referrals = 1 Voucher\n"
            f"📦 <b>Pool:</b> {pool or 0} rewards remaining\n\n"
            f"📊 <b>YOUR PROGRESS:</b>\n"
        ) +
        f"<code>{bar}</code> <b>{progress}/{sans_normal(str(goal))}</b>\n\n" +
        sh("━━━━━━━━━━━━━━━━━━━━━━\n") +
        sb("🚀 <i>The more you invite, the more you earn!</i>")
    )
    
    if message.from_user.id == (await message.bot.get_me()).id:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "view_refer_rules")
async def view_refer_rules_cb(callback: CallbackQuery):
    rules = (
        sh("📜 <b>REFERRAL PROGRAM RULES</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n") +
        sb(
            "1️⃣ <b>Unique Users:</b> Only new users who have never used the bot count.\n\n"
            "2️⃣ <b>No Self-Refer:</b> Creating multiple accounts to refer yourself will lead to a <b>Permanent Ban</b>. 🚫\n\n"
            "3️⃣ <b>Fake Referrals:</b> Use of bots or fake accounts is strictly prohibited.\n\n"
            "4️⃣ <b>Rewards:</b> Once you reach the goal, click 'Claim Reward' to get your voucher instantly.\n\n"
            "✅ <i>Fair play ensures everyone gets their rewards!</i>"
        )
    )
    await callback.message.edit_text(rules, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=bold_sans("🔙 Back"), callback_data="back_to_refer")]]))
    await callback.answer()

@router.callback_query(F.data == "view_leaderboard")
async def view_leaderboard_cb(callback: CallbackQuery, session: AsyncIOMotorDatabase):
    from database.requests import get_top_referrers
    top_users = await get_top_referrers(session)
    
    if not top_users:
        return await callback.answer(bold_sans("🏆 Leaderboard is empty. Start referring to lead!"), show_alert=True)
        
    text = sh("🏆 <b>TOP REFERRAL LEADERS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n")
    for i, user in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▪️"
        name = user.full_name[:15] + ".." if len(user.full_name) > 15 else user.full_name
        text += sb(f"{medal} <b>{name}</b> — ") + f"<code>{user.referral_count}</code> " + sb("Invites\n")
        
    text += sh("\n━━━━━━━━━━━━━━━━━━━━━━\n") + sb("🚀 <i>Can you make it to the top 10?</i>")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=bold_sans("🔙 Back"), callback_data="back_to_refer")]])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "back_to_refer")
async def back_to_refer_cb(callback: CallbackQuery, session: AsyncIOMotorDatabase):
    await show_referral_menu(callback.message, session, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "view_referral_link")
async def view_referral_link_cb(callback: CallbackQuery):
    import urllib.parse
    bot_me = await callback.bot.get_me()
    link = f"https://t.me/{bot_me.username}?start={callback.from_user.id}"
    
    share_text = "🎁 Hey! Join this bot and get premium Shein coupons for free! 🛒✨"
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(link)}&text={urllib.parse.quote(share_text)}"
    
    ref_link_msg = (
        sh("🔗 <b>YOUR INVITE LINK</b>\n") +
        sh("━━━━━━━━━━━━━━━━━━━━━━\n\n") +
        f"<code>{link}</code>\n\n" +
        sb("💡 Share this link with your friends. Once they start the bot, your referral progress increases automatically!\n\n") +
        sb("👇 <b>Click the button below to share directly:</b>")
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=bold_sans("📤 Share Invite Link"), url=share_url)],
        [InlineKeyboardButton(text=bold_sans("🔙 Back"), callback_data="back_to_refer")]
    ])
    
    try:
        await callback.message.edit_text(ref_link_msg, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await callback.message.answer(ref_link_msg, reply_markup=kb, disable_web_page_preview=True)
        
    await callback.answer()

@router.callback_query(F.data == "my_redeemed_rewards")
async def my_redeemed_rewards_cb(callback: CallbackQuery, session: AsyncIOMotorDatabase):
    rewards = await get_user_redeemed_rewards(session, callback.from_user.id)
    if not rewards: return await callback.answer(bold_sans("❌ No rewards redeemed yet."), show_alert=True)
    text = sh("🎟️ <b>REDEEMED VOUCHERS</b>\n\n")
    for r in rewards: text += f"▪️ <code>{r.code}</code> ({sans_normal(r.created_at.strftime('%d %b'))})\n"
    await callback.message.answer(text); await callback.answer()

@router.callback_query(F.data == "redeem_referral")
async def redeem_referral_cb(callback: CallbackQuery, session: AsyncIOMotorDatabase):
    user = await get_user_by_id(session, callback.from_user.id); goal = int(await get_setting(session, "refer_goal", "3"))
    if user.referral_count < goal: return await callback.answer(bold_sans(f"❌ Need {goal} referrals!"), show_alert=True)
    reward = await get_available_reward(session)
    if not reward: return await callback.answer(bold_sans("❌ Reward pool empty. Admin notified!"), show_alert=True)
    await use_reward(session, reward.id, user.id); await update_user(session, user.id, referral_count=user.referral_count - goal)
    
    success_reward_msg = sh("🎉 <b>SUCCESS!</b>\n\n") + sb(f"Your reward voucher: <code>{reward.code}</code>\n\nUse it now! 🚀")
    await callback.message.answer(success_reward_msg)
    await callback.answer(bold_sans("Claimed!")); await callback.message.delete()

@router.message(F.text == BTN_RECOVER_VOUCHER)
async def recover_voucher_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(UserStates.recover_order_id)
    recovery_start_msg = sh("🔍 <b>Voucher Recovery</b>\n\n") + sb("To recover your codes or check order status, please send your <b>Order ID</b> or <b>UTR Number</b>:")
    await message.answer(recovery_start_msg)

@router.message(UserStates.recover_order_id)
async def recover_order_process(message: Message, state: FSMContext, bot: Bot, session: AsyncIOMotorDatabase):
    if message.text in MENU_BUTTONS: await state.clear(); return
    text = message.text.strip() if message.text else ""
    
    utr_match = re.search(r'\d{12}', text)
    if utr_match: search_term = utr_match.group(0)
    else: search_term = text

    tx = await find_transaction_robust(session, search_term)
    if tx and tx.user_id != message.from_user.id:
        count = await increment_user_warning(session, message.from_user.id); await state.clear()
        if count >= 5: 
            from middlewares.checks import USER_CACHE
            USER_CACHE.pop(message.from_user.id, None)
            banned_err = sh("🚫 <b>BANNED</b>\n\n") + sb("Fraudulent intent detected.")
            await message.answer(banned_err)
            return
        violation_err = sh("🚨 <b>SECURITY VIOLATION</b>\n\n") + sb(f"That ID does not belong to you. Attempt logged. ({count}/5 strikes)")
        return await message.answer(violation_err)
    
    if not tx: 
        not_found_err = sh("❌ <b>ORDER NOT FOUND</b>\n\n") + sb("Check your ID and re-send. Make sure you are using the correct Order ID (SHN-...) or UTR.")
        return await message.answer(not_found_err)
    
    tx, items = await get_transaction_with_items(session, tx.id)
    order_id = tx.provider_payment_charge_id or f'TXN-{tx.id}'; status = tx.status; await state.clear()
    
    if status == 'completed':
        codes = "\n".join([f"   ▪️ {sans_normal(cat.name)}: <code>{c.code}</code>" for c, cat in items])
        recovered_msg = (
            sh("✅ <b>VOUCHER RECOVERED</b>\n━━━━━━━━━━━━━━━━━━━━━━\n") +
            sb(
                f"📋 <b>ID:</b> <code>{order_id}</code>\n"
                f"💰 <b>Value:</b> ₹{tx.amount}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎫 <b>CODES:</b>\n{codes}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🚀 <i>Happy Shopping!</i>"
            )
        )
        await message.answer(recovered_msg)
    elif status == 'pending' and tx.payment_proof_id and ("UTR:" in tx.payment_proof_id):
        pending_verif_msg = (
            sh("⏳ <b>UNDER VERIFICATION</b>\n━━━━━━━━━━━━━━━━━━━━━━\n") +
            sb(
                f"📋 <b>ID:</b> <code>{order_id}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Proof received.\n"
                f"⏳ Admin is verifying (5-15 mins).\n\n"
                f"<i>You'll receive codes as soon as approved!</i>"
            )
        )
        await message.answer(pending_verif_msg)
    elif status == 'pending':
        photo_id = None
        if tx.payment_proof_id and tx.payment_proof_id.startswith("FILE:"):
            photo_id = tx.payment_proof_id.split(":", 1)[1]
            await state.update_data(order_id=order_id, tx_id=tx.id, total_price=float(tx.amount), photo_id=photo_id)
            await state.set_state(UserStates.waiting_for_utr)
            resume_utr_msg = (
                sh("🔄 <b>RESUME: UTR REQUIRED</b>\n━━━━━━━━━━━━━━━━━━━━━━\n") +
                sb(
                    f"📋 <b>ID:</b> <code>{order_id}</code>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"✅ Screenshot was saved.\n"
                    f"📍 <b>Please send your 12-digit UTR now:</b>"
                )
            )
            await message.answer(resume_utr_msg)
        else:
            cat = items[0][1] if items else None
            qr_photo = cat.qr_file_id if (cat and cat.qr_file_id) else None
            cat_id = cat.id if cat else None
            cat_name = cat.name if cat else "(reserved order)"
            
            await state.update_data(order_id=order_id, tx_id=tx.id, total_price=float(tx.amount), quantity=tx.quantity, cat_name=cat_name, cat_id=cat_id)
            await state.set_state(UserStates.waiting_for_payment_screenshot)
            
            img_path = os.getenv("PAYMENT_METHOD_IMAGE_PATH", "assets/payment.jpg")
            cap = (
                sh("🔄 <b>RESUME CHECKOUT</b>\n━━━━━━━━━━━━━━━━━━━━━━\n") +
                sb(
                    f"📋 <b>ID:</b> <code>{order_id}</code>\n"
                    f"💰 <b>Payable:</b> <b>₹{tx.amount}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"1️⃣ Scan QR & Pay\n"
                    f"2️⃣ Upload Screenshot\n"
                    f"3️⃣ Send UTR\n\n"
                    f"<i>Pay quickly to keep your stock!</i>"
                )
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=bold_sans("❌ Cancel"), callback_data=f"cancel_order_tx_{tx.id}")]])
            
            if qr_photo:
                await message.answer_photo(photo=qr_photo, caption=cap, reply_markup=kb)
            elif os.path.exists(img_path):
                await message.answer_photo(photo=FSInputFile(img_path), caption=cap, reply_markup=kb)
            else:
                await message.answer(cap, reply_markup=kb)
    else: 
        expired_msg = sh("❌ <b>STATUS: ") + bold_sans(status.upper()) + sh("</b>\n\n") + sb("This session has expired. Start a fresh purchase.")
        await message.answer(expired_msg)

@router.message(F.text == BTN_HELP_SUPPORT)
async def user_faq(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear()
    contacts = await get_support_contacts(session)
    text = (
        sh("💡 <b>SHEIN SHOP HELP CENTER</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n") +
        sb(
            "💎 <b>How to Buy?</b> Select package → Pay → Submit UTR → Get Codes.\n\n"
            "💳 <b>Payments:</b> We accept all UPI apps. Scan & Pay the exact total.\n\n"
            "🔢 <b>UTR:</b> The 12-digit number from your payment confirmation.\n\n"
            "🎥 <b>Policy:</b> You <u>MUST</u> have an uncut screen recording to get support.\n\n"
            "🔄 <b>Lost Codes?</b> Use 'Recover Voucher' with your Order ID.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Select a support agent below:</b>"
        )
    )
    kb = [[InlineKeyboardButton(text=f"💬 {bold_sans(c.label)}", url=f"https://t.me/{c.username}")] for c in contacts]
    if not kb: kb = [[InlineKeyboardButton(text=bold_sans("💬 Helpdesk Bot"), url="https://t.me/helpdesk_coupon_bot")]]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.message(F.text == BTN_JOIN_CHANNEL)
async def user_channel(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear()
    channels = await get_channels(session)
    if not channels: 
        no_channels_msg = sh("📢 <b>OFFICIAL CHANNELS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n") + sb("Stay tuned! We are setting up our official communication hubs. 🔄")
        return await message.answer(no_channels_msg)
    text = (
        sh("📢 <b>OFFICIAL ANNOUNCEMENT CHANNELS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n") +
        sb(
            "Don't miss out! Join our community to stay ahead with:\n\n"
            "⚡ <b>Instant Restock Alerts:</b> Buy before stock ends.\n"
            "🎁 <b>Exclusive Giveaways:</b> Free vouchers for members.\n"
            "🔥 <b>Secret Discount Codes:</b> Flash sales & extra % off.\n"
            "🚀 <b>Shop Updates:</b> Be the first to know about new stock.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👇 <b>Select a channel below to join:</b>"
        )
    )
    kb = [[InlineKeyboardButton(text=f"📢 {bold_sans(ch.name.upper())}", url=ch.invite_link)] for ch in channels]
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.message(F.text == BTN_MY_PROFILE)
async def user_profile(message: Message, state: FSMContext, session: AsyncIOMotorDatabase):
    await state.clear()
    user_q   = get_user_by_id(session, message.from_user.id)
    counts_q = get_user_order_counts(session, message.from_user.id)
    user, (bought, spent) = await asyncio.gather(user_q, counts_q)
    
    if not user:
        return await message.answer(sh("❌ ") + sb("Error. Try /start"))
    
    status_icon = "🟢" if not user.is_blocked and not user.is_suspicious else "⚠️" if user.is_suspicious else "🔴"
    status_text = "Blacklisted" if user.is_blocked else "Flagged" if user.is_suspicious else "Active Member"
    
    text = (
        sh("👤 <b>USER DASHBOARD</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n") +
        sb(
            f"👋 <b>Welcome back, {message.from_user.first_name}!</b>\n\n"
            f"🆔 <b>Account ID:</b> <code>{user.id}</code>\n"
            f"📅 <b>Member Since:</b> {user.created_at.strftime('%d %b %Y')}\n"
            f"🛡️ <b>Account Status:</b> {status_icon} {status_text}\n\n"
            f"📊 <b>PURCHASE STATS</b>\n"
            f"├─ 🛍️ <b>Orders:</b> <code>{bought}</code>\n"
            f"└─ 💸 <b>Invested:</b> <b>₹{float(spent):.2f}</b>\n\n"
            f"👥 <b>REFERRAL STATS</b>\n"
            f"├─ 🤝 <b>Invites:</b> <code>{user.referral_count}</code>\n"
        ) +
        f"├─ 🔗 <b>Link:</b> <a href='https://t.me/{(await message.bot.get_me()).username}?start={user.id}'>" +
        sb("Get Invite Link") + "</a>\n\n" +
        sh("━━━━━━━━━━━━━━━━━━━━━━\n") +
        sb("🚀 <i>Thank you for being part of our community!</i>")
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=bold_sans("🛍️ My Orders"), callback_data="back_to_history"), 
         InlineKeyboardButton(text=bold_sans("🤝 Invite Friends"), callback_data="view_referral_link")],
        [InlineKeyboardButton(text=bold_sans("🆘 Contact Support"), callback_data="view_support_from_profile")]
    ])
    
    await message.answer(text, reply_markup=kb, disable_web_page_preview=True)

@router.callback_query(F.data == "view_support_from_profile")
async def view_support_from_profile_cb(callback: CallbackQuery, state: FSMContext, session: AsyncIOMotorDatabase):
    await user_faq(callback.message, state, session)
    await callback.answer()

@router.callback_query(F.data.startswith("show_codes_"))
async def show_codes_handler(callback: CallbackQuery, session: AsyncIOMotorDatabase):
    tx_id = int(callback.data.split("_")[-1])
    tx, items = await get_transaction_with_items(session, tx_id)
    if not tx:
        return await callback.answer("❌ Order not found.", show_alert=True)
    if tx.user_id != callback.from_user.id:
        return await callback.answer("❌ You do not have permission to view this order.", show_alert=True)
    
    # Generate codes list
    codes_list = "\n".join([f"  🔑 <b>{sans_normal(cat.name)}:</b> <code>{c.code}</code>" for c, cat in items])
    tx_charge_id = tx.provider_payment_charge_id or f"TXN-{tx.id}"
    
    # Load dynamic instructions from coupon's category, fall back to default
    cat = items[0][1] if items else None
    instructions = cat.instructions if (cat and cat.instructions) else DEFAULT_INSTRUCTIONS
    
    delivery_msg = (
        sh("🎉 <b>PAYMENT APPROVED & COMPLETED!</b>\n") +
        sh("━━━━━━━━━━━━━━━━━━━━━━━━\n") +
        sb(f"📋 <b>Order ID:</b> <code>{tx_charge_id}</code>\n") +
        sb(f"💰 <b>Total Paid:</b> <b>₹{float(tx.amount):.2f}</b>\n") +
        sh("━━━━━━━━━━━━━━━━━━━━━━━━\n\n") +
        sh("🎫 <b>YOUR COUPON CODE(S):</b>\n") +
        f"{codes_list}\n\n" +
        sh("━━━━━━━━━━━━━━━━━━━━━━━━\n") +
        instructions
    )
    
    try:
        await callback.message.edit_text(delivery_msg, disable_web_page_preview=True)
    except Exception:
        try:
            await callback.message.answer(delivery_msg, disable_web_page_preview=True)
        except Exception:
            pass
    await callback.answer()
