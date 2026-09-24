# -*- coding: utf-8 -*-
"""
ربات تلگرامی.
کتابخونه: python-telegram-bot >= 22.7  (برای پشتیبانی از style رنگی دکمه‌ها)
نصب: pip install -r requirements.txt
اجرا: python bot.py
"""

import logging

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    MessageEntity,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CopyTextButton,
    LinkPreviewOptions,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

import config
import db

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


# ============================================================
#  توابع کمکی برای متن‌های غنی (ایموجی پریمیوم + بولد)
# ============================================================
def make_custom_emoji_entities(text: str, emoji_map: dict) -> list:
    """تو متن دنبال هر ایموجی می‌گرده و entity ایموجی پریمیوم مربوطه رو می‌سازه."""
    entities = []
    for emoji, custom_id in emoji_map.items():
        idx = text.find(emoji)
        if idx == -1:
            continue
        offset = len(text[:idx].encode("utf-16-le")) // 2
        length = len(emoji.encode("utf-16-le")) // 2
        entities.append(
            MessageEntity(
                type=MessageEntity.CUSTOM_EMOJI,
                offset=offset,
                length=length,
                custom_emoji_id=custom_id,
            )
        )
    return entities


def make_bold_entities(text: str, substrings: list) -> list:
    """
    برای هر رشته (به ترتیب ظاهرشدنشون تو متن) یه entity بولد می‌سازه.
    جستجو به‌صورت ترتیبی/تجمعی انجام می‌شه تا با اعداد تکراری (مثل چند تا "0") قاطی نشه.
    """
    entities = []
    cursor = 0
    for s in substrings:
        idx = text.find(s, cursor)
        if idx == -1:
            continue
        offset = len(text[:idx].encode("utf-16-le")) // 2
        length = len(s.encode("utf-16-le")) // 2
        entities.append(MessageEntity(type=MessageEntity.BOLD, offset=offset, length=length))
        cursor = idx + len(s)
    return entities


async def get_sticker_file_id(context: ContextTypes.DEFAULT_TYPE, set_name: str, emoji: str = None) -> str:
    """استیکر رو از روی اسم پک می‌گیره؛ اولین موردی که ایموجیش مچ باشه رو برمی‌گردونه."""
    sticker_set = await context.bot.get_sticker_set(set_name)
    stickers = sticker_set.stickers
    if emoji:
        for s in stickers:
            if s.emoji == emoji:
                return s.file_id
    return stickers[0].file_id


# ============================================================
#  منوی اصلی (دکمه‌های رنگی)
# ============================================================
BTN_ACCOUNT = "👤 حساب کاربری"
BTN_WITHDRAW = "💰 برداشت"
BTN_REFERRAL = "👥 زیرمجموعه گیری"
BTN_GUIDE = "❗️راهنما"

main_menu = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_ACCOUNT, style="danger")],
        [
            KeyboardButton(BTN_WITHDRAW, style="primary"),
            KeyboardButton(BTN_REFERRAL, style="success"),
        ],
        [KeyboardButton(BTN_GUIDE)],
    ],
    resize_keyboard=True,
)


# ============================================================
#  پیام خوش‌آمدگویی
# ============================================================
WELCOME_TEXT = "سلام 👀 \nبه ربات ما خوش‌اومدی.\n\nخدمات مورد نظرت رو انتخاب کن 👇"
WELCOME_ENTITIES = [
    MessageEntity(type=MessageEntity.CUSTOM_EMOJI, offset=5, length=2, custom_emoji_id="5210956306952758910"),
    MessageEntity(type=MessageEntity.CUSTOM_EMOJI, offset=61, length=2, custom_emoji_id="5470177992950946662"),
]


# ============================================================
#  عضویت اجباری
# ============================================================
async def get_unjoined_channels(bot, user_id: int):
    unjoined = []
    for ref in db.get_force_channels():
        try:
            member = await bot.get_chat_member(chat_id=ref, user_id=user_id)
            if member.status in ("left", "kicked"):
                unjoined.append(ref)
        except Exception as e:
            logging.warning("چک عضویت کانال %s ناموفق بود: %s", ref, e)
    return unjoined


def build_join_keyboard(unjoined: list) -> InlineKeyboardMarkup:
    rows = []
    for ref in unjoined:
        username = ref.lstrip("@")
        rows.append(
            [InlineKeyboardButton(f"📢 عضویت در کانال", url=f"https://t.me/{username}", style="primary")]
        )
    rows.append([InlineKeyboardButton("✅ عضو شدم", callback_data="check_join", style="success")])
    return InlineKeyboardMarkup(rows)


async def force_join_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """اگه کاربر عضو همه‌ی کانال‌های اجباری نباشه، پیام عضویت رو می‌فرسته و False برمی‌گردونه."""
    user = update.effective_user
    unjoined = await get_unjoined_channels(context.bot, user.id)
    if not unjoined:
        return True
    await update.effective_message.reply_text(
        "⚠️ برای استفاده از ربات، اول باید عضو کانال(های) زیر بشی:",
        reply_markup=build_join_keyboard(unjoined),
    )
    return False


async def handle_check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    unjoined = await get_unjoined_channels(context.bot, user.id)
    if unjoined:
        await query.answer("هنوز عضو همه‌ی کانال‌ها نشدی ❌", show_alert=True)
        return

    await query.answer("عضویت تایید شد ✅")
    try:
        await query.message.delete()
    except Exception:
        pass
    await context.bot.send_message(
        chat_id=user.id,
        text="خوش اومدی 🎉 از منوی زیر یکی رو انتخاب کن:",
        reply_markup=main_menu,
    )


# ============================================================
#  استیکرها
# ============================================================
ACCOUNT_STICKER_EMOJI = "🤔"
GUIDE_STICKER_EMOJI = "😴"
REFERRAL_STICKER_EMOJI = "👨‍💻"


# ============================================================
#  /start + اعتبار دادن به معرف
# ============================================================
async def notify_referrer(context: ContextTypes.DEFAULT_TYPE, referrer_id: int, invitee):
    """به معرف پیام می‌ده که فلان کاربر با موفقیت زیرمجموعه‌ش شد؛ رو اسم بزنه می‌ره پروفایلش."""
    first_name = invitee.first_name or "کاربر"
    username_part = f" (@{invitee.username})" if invitee.username else ""
    text = f"کاربر {first_name}{username_part} با موفقیت به زیرمجموعه شما اضافه شد ✅"

    name_offset = len(("کاربر ").encode("utf-16-le")) // 2
    name_length = len(first_name.encode("utf-16-le")) // 2
    entities = [
        MessageEntity(
            type=MessageEntity.TEXT_MENTION,
            offset=name_offset,
            length=name_length,
            user=invitee,
        )
    ]
    try:
        await context.bot.send_message(chat_id=referrer_id, text=text, entities=entities)
    except Exception as e:
        logging.warning("اطلاع‌رسانی به معرف ناموفق بود: %s", e)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    row, created = db.get_or_create_user(user.id, user.username or user.first_name)

    # اگه کاربر جدید با لینک یکی دیگه اومده باشه، به معرف پاداش می‌دیم
    if created and context.args:
        try:
            referrer_id = int(context.args[0])
        except (ValueError, IndexError):
            referrer_id = None

        if referrer_id and referrer_id != user.id and db.get_user(referrer_id) is not None:
            db.add_balance(referrer_id, config.REFERRAL_REWARD)
            db.increment_referral_count(referrer_id)
            await notify_referrer(context, referrer_id, user)

    if not await force_join_gate(update, context):
        return

    await update.message.reply_text(WELCOME_TEXT, entities=WELCOME_ENTITIES, reply_markup=main_menu)


# ============================================================
#  حساب کاربری
# ============================================================
async def handle_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_join_gate(update, context):
        return

    user = update.effective_user
    row, _ = db.get_or_create_user(user.id, user.username or user.first_name)

    try:
        sticker_id = await get_sticker_file_id(context, config.STICKER_SET, ACCOUNT_STICKER_EMOJI)
        await update.message.reply_sticker(sticker_id)
    except Exception as e:
        logging.warning("ارسال استیکر حساب کاربری ناموفق بود: %s", e)

    balance_str = config.fmt_amount(f"{row['balance']:.2f}")
    min_withdraw_str = config.fmt_amount(config.MIN_WITHDRAW)

    text = (
        f"👤 آیدی شما: {row['user_id']}\n"
        f"💰 موجودی شما: {balance_str}\n"
        f"👥 تعداد زیرمجموعه‌های شما: {row['referral_count']}\n"
        f"💸 حداقل مبلغ برداشت: {min_withdraw_str}"
    )

    entities = make_custom_emoji_entities(
        text,
        {
            "👤": "5427168083074628963",
            "💰": "5409048419211682843",
            "👥": "5372926953978341366",
            "💸": "5375129357373165375",
        },
    ) + make_bold_entities(
        text,
        [str(row["user_id"]), balance_str, str(row["referral_count"]), min_withdraw_str],
    )

    referral_link = f"https://t.me/{config.BOT_USERNAME}?start={row['user_id']}"
    copy_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📝 کپی لینک دعوت", copy_text=CopyTextButton(text=referral_link), style="primary")]]
    )

    await update.message.reply_text(text, entities=entities, reply_markup=copy_button)


# ============================================================
#  برداشت
# ============================================================
async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_join_gate(update, context):
        return

    user = update.effective_user
    row, _ = db.get_or_create_user(user.id, user.username or user.first_name)

    if row["balance"] < config.MIN_WITHDRAW:
        await update.message.reply_text(
            "❌ موجودی شما کمتر از حداقل برداشت است.\n"
            f"حداقل برداشت : {config.fmt_amount(config.MIN_WITHDRAW)}"
        )
        return

    db.set_awaiting_wallet(user.id, True)
    await update.message.reply_text(
        "لطفاً آدرس ولت خودتون رو با شبکه‌ی BEP20 (BSC) ارسال کنید.\n"
        "برای راهنمای گرفتن آدرس، دکمه «راهنما» رو بزنید."
    )


PAYMENT_SUCCESS_TEXT = "✅ پرداخت شما با موفقیت انجام شد!\n\nمبلغ درخواستی به ولت شما واریز گردید."
PAYMENT_SUCCESS_ENTITIES = [
    MessageEntity(type=MessageEntity.CUSTOM_EMOJI, offset=0, length=1, custom_emoji_id="5206607081334906820"),
    MessageEntity(type=MessageEntity.BOLD, offset=2, length=30),
]

WRONG_WALLET_TEXT = (
    "❌ ولت شما اشتباه بوده است.\n\n"
    "لطفاً آدرس درست ولتتون (شبکه BEP20) رو دوباره برای ربات ارسال کنید."
)


async def handle_withdraw_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی ادمین توی کانال روی «واریز شد» یا «ولت اشتباه است» می‌زنه."""
    query = update.callback_query
    admin = query.from_user

    if admin.id not in config.ADMIN_IDS:
        await query.answer("⛔️ شما اجازه‌ی این کار رو ندارید.", show_alert=True)
        return

    action, wid_str = query.data.split(":")
    wid = int(wid_str)
    withdrawal = db.get_withdrawal(wid)

    if withdrawal is None:
        await query.answer("درخواست پیدا نشد.", show_alert=True)
        return
    if withdrawal["status"] != "pending":
        await query.answer("این درخواست قبلاً پردازش شده.", show_alert=True)
        return

    target_user_id = withdrawal["user_id"]

    if action == "paid":
        db.add_balance(target_user_id, -withdrawal["amount"])
        db.update_withdrawal_status(wid, "paid")
        await query.answer("تایید شد ✅")
        try:
            await query.edit_message_text(query.message.text + "\n\n✅ پرداخت شد")
        except Exception:
            pass
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=PAYMENT_SUCCESS_TEXT,
                entities=PAYMENT_SUCCESS_ENTITIES,
            )
        except Exception as e:
            logging.warning("اطلاع‌رسانی پرداخت به کاربر ناموفق بود: %s", e)

    elif action == "wrong":
        db.update_withdrawal_status(wid, "wrong_wallet")
        db.set_awaiting_wallet(target_user_id, True)  # موجودی دست‌نخورده می‌مونه، دوباره منتظر آدرس درست می‌شیم
        await query.answer("ثبت شد")
        try:
            await query.edit_message_text(query.message.text + "\n\n❌ ولت اشتباه بود")
        except Exception:
            pass
        try:
            await context.bot.send_message(chat_id=target_user_id, text=WRONG_WALLET_TEXT)
        except Exception as e:
            logging.warning("اطلاع‌رسانی ولت اشتباه به کاربر ناموفق بود: %s", e)


# ============================================================
#  زیرمجموعه‌گیری
# ============================================================
async def handle_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_join_gate(update, context):
        return

    user = update.effective_user
    row, _ = db.get_or_create_user(user.id, user.username or user.first_name)

    try:
        sticker_id = await get_sticker_file_id(context, config.STICKER_SET, REFERRAL_STICKER_EMOJI)
        await update.message.reply_sticker(sticker_id)
    except Exception as e:
        logging.warning("ارسال استیکر زیرمجموعه‌گیری ناموفق بود: %s", e)

    referral_link = f"https://t.me/{config.BOT_USERNAME}?start={row['user_id']}"
    reward_str = config.fmt_amount(config.REFERRAL_REWARD)

    text = (
        "📢 با دعوت دوستانت درآمد کسب کن!\n\n"
        f"دوستانت رو به ربات دعوت کن و به‌ازای هر نفری که دعوت می‌کنی "
        f"{reward_str} 💰 پاداش بگیر و درآمد واقعی داشته باش! 🎁\n\n"
        "🔗 لینک اختصاصی دعوت شما:\n"
        f"{referral_link}\n\n"
        "⏳ فرصت رو از دست نده! هرچه افراد بیشتری دعوت کنی، سریع‌تر موجودیت افزایش پیدا می‌کنه "
        "و می‌تونی برداشتش کنی. ✅\n\n"
        f"👥 تعداد زیرمجموعه‌های شما: {row['referral_count']}"
    )

    entities = make_custom_emoji_entities(
        text,
        {
            "📢": "5244837092042750681",
            "💰": "5409048419211682843",
            "🔗": "5375129357373165375",
            "⏳": "5451646226975955576",
            "✅": "5406756500108501710",
        },
    ) + make_bold_entities(text, ["با دعوت دوستانت درآمد کسب کن!", reward_str, str(row["referral_count"])])

    copy_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📝 کپی لینک دعوت", copy_text=CopyTextButton(text=referral_link), style="primary")]]
    )

    await update.message.reply_text(
        text,
        entities=entities,
        reply_markup=copy_button,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


# ============================================================
#  راهنما
# ============================================================
GUIDE_TEXT = (
    "🌐 آموزش دریافت آدرس شبکه BEP20 از تراست ولت\n\n"
    "برای برداشت وجه، باید آدرس کیف پول خودتون با شبکه‌ی BEP20 (BSC) رو ارسال کنید. "
    "مراحل زیر رو دنبال کنید:\n\n"
    "۱. اپلیکیشن Trust Wallet رو باز کنید\n"
    "۲. دکمه‌ی Receive (دریافت) رو بزنید\n"
    "۳. ارز BNB رو انتخاب کنید (شبکه‌ش به‌صورت پیش‌فرض BEP20 هست)\n"
    "✅ آدرسی که نمایش داده می‌شه رو کپی کنید (با آیکون کپی کنار آدرس)\n\n"
    "🔗 توجه داشته باشید آدرس شبکه‌ی BEP20 برای همه‌ی ارزها یکسانه.\n\n"
    "❌ مهم: اگه شبکه‌ی اشتباه (مثل ERC20 یا TRC20) رو انتخاب کنید، امکان واریز وجود نداره "
    "و ممکنه دارایی‌تون از دست بره.\n\n"
    "بعد از کپی کردن آدرس، اون رو دقیقاً همون‌طور که کپی کردید (بدون فاصله یا کاراکتر اضافه) "
    "برای ربات ارسال کنید."
)
GUIDE_ENTITIES = [
    MessageEntity(type=MessageEntity.CUSTOM_EMOJI, offset=0, length=2, custom_emoji_id="5447410659077661506"),
    MessageEntity(type=MessageEntity.BOLD, offset=3, length=41),
    MessageEntity(type=MessageEntity.BOLD, offset=98, length=11),
    MessageEntity(type=MessageEntity.BOLD, offset=163, length=12),
    MessageEntity(type=MessageEntity.BOLD, offset=198, length=7),
    MessageEntity(type=MessageEntity.BOLD, offset=231, length=3),
    MessageEntity(type=MessageEntity.CUSTOM_EMOJI, offset=285, length=1, custom_emoji_id="5375129357373165375"),
    MessageEntity(type=MessageEntity.CUSTOM_EMOJI, offset=351, length=2, custom_emoji_id="5375129357373165375"),
    MessageEntity(type=MessageEntity.CUSTOM_EMOJI, offset=415, length=1, custom_emoji_id="5465665476971471368"),
    MessageEntity(type=MessageEntity.BOLD, offset=417, length=4),
]


async def handle_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await force_join_gate(update, context):
        return

    try:
        sticker_id = await get_sticker_file_id(context, config.STICKER_SET, GUIDE_STICKER_EMOJI)
        await update.message.reply_sticker(sticker_id)
    except Exception as e:
        logging.warning("ارسال استیکر راهنما ناموفق بود: %s", e)

    await update.message.reply_text(GUIDE_TEXT, entities=GUIDE_ENTITIES)


# ============================================================
#  پنل مدیریت (فقط برای ADMIN_IDS)
# ============================================================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in config.ADMIN_IDS:
        return  # کاربر عادی اصلاً نمی‌فهمه همچین دستوری وجود داره

    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📨 ارسال پیام همگانی", callback_data="admin_broadcast", style="primary")],
            [InlineKeyboardButton("➕ افزودن کانال عضویت اجباری", callback_data="admin_addchannel", style="success")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back", style="danger")],
        ]
    )
    await update.message.reply_text("🛠 پنل مدیریت ربات", reply_markup=buttons)


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    if user.id not in config.ADMIN_IDS:
        await query.answer("⛔️ شما ادمین نیستید.", show_alert=True)
        return

    await query.answer()

    if query.data == "admin_broadcast":
        context.user_data["admin_awaiting"] = "broadcast"
        await query.message.reply_text("متن پیامی که می‌خوای برای همه‌ی کاربرا ارسال بشه رو بفرست:")

    elif query.data == "admin_addchannel":
        context.user_data["admin_awaiting"] = "add_channel"
        await query.message.reply_text(
            "یوزرنیم یا لینک کانال رو بفرست (مثلاً @channel یا https://t.me/channel).\n"
            "⚠️ ربات باید ادمین اون کانال باشه تا بتونه عضویت رو چک کنه."
        )

    elif query.data == "admin_back":
        context.user_data["admin_awaiting"] = None
        try:
            await query.message.delete()
        except Exception:
            pass


async def handle_admin_broadcast_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data["admin_awaiting"] = None
    user_ids = db.get_all_user_ids()
    sent = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception:
            pass  # کاربرهایی که ربات رو بلاک کردن یا پیام نگرفتن، رد می‌شن
    await update.message.reply_text(f"پیام برای {sent} کاربر ارسال شد ✅")


async def handle_admin_addchannel_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data["admin_awaiting"] = None
    ref = text.strip()
    if ref.startswith("https://t.me/"):
        ref = "@" + ref.split("https://t.me/")[-1]
    elif not ref.startswith("@"):
        ref = "@" + ref
    db.add_force_channel(ref)
    await update.message.reply_text(f"کانال {ref} به لیست عضویت اجباری اضافه شد ✅")


# ============================================================
#  هندلر یکپارچه‌ی متن (منو + آدرس ولت + ورودی‌های ادمین)
# ============================================================
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    row, _ = db.get_or_create_user(user.id, user.username or user.first_name)

    # ۱. اگه منتظر آدرس ولت این کاربر هستیم
    if row["awaiting_wallet"]:
        wallet = text.strip()
        if len(wallet) < 20:
            await update.message.reply_text("آدرس واردشده معتبر به نظر نمی‌رسه. دوباره امتحان کن.")
            return

        amount = row["balance"]
        wid = db.create_withdrawal(user.id, amount, wallet)
        db.set_awaiting_wallet(user.id, False)

        channel_text = (
            "🔔 درخواست برداشت جدید\n\n"
            f"👤 کاربر: {user.first_name} (@{user.username or '-'})\n"
            f"🆔 آیدی: {user.id}\n"
            f"💰 مبلغ: {config.fmt_amount(amount)}\n"
            f"🔗 ولت: {wallet}"
        )
        decision_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ واریز شد", callback_data=f"paid:{wid}", style="success"),
                    InlineKeyboardButton("❌ ولت شما اشتباه است", callback_data=f"wrong:{wid}", style="danger"),
                ]
            ]
        )
        try:
            await context.bot.send_message(
                chat_id=config.WITHDRAW_CHANNEL, text=channel_text, reply_markup=decision_buttons
            )
        except Exception as e:
            logging.error("ارسال به کانال برداشت ناموفق بود: %s", e)

        await update.message.reply_text("✅ درخواست برداشت شما ثبت شد. منتظر تایید بمونید.")
        return

    # ۲. اگه ادمین منتظر ورودی خاصیه (broadcast / افزودن کانال)
    admin_state = context.user_data.get("admin_awaiting")
    if admin_state and user.id in config.ADMIN_IDS:
        if admin_state == "broadcast":
            await handle_admin_broadcast_input(update, context, text)
            return
        if admin_state == "add_channel":
            await handle_admin_addchannel_input(update, context, text)
            return

    # ۳. بقیه‌ی موارد -> دکمه‌های منوی اصلی
    if text == BTN_ACCOUNT:
        await handle_account(update, context)
    elif text == BTN_WITHDRAW:
        await handle_withdraw(update, context)
    elif text == BTN_REFERRAL:
        await handle_referral(update, context)
    elif text == BTN_GUIDE:
        await handle_guide(update, context)
    else:
        await update.message.reply_text("متوجه پیامت نشدم، از منو استفاده کن 🙏")


# ============================================================
#  اجرای ربات
# ============================================================
def main():
    db.init_db()
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))

    app.add_handler(CallbackQueryHandler(handle_check_join, pattern=r"^check_join$"))
    app.add_handler(CallbackQueryHandler(handle_withdraw_decision, pattern=r"^(paid|wrong):"))
    app.add_handler(CallbackQueryHandler(handle_admin_callback, pattern=r"^admin_"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    print("ربات روشن شد...")
    app.run_polling()


if __name__ == "__main__":
    main()
