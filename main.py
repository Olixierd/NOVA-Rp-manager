import os
from threading import Thread
from flask import Flask

app = Flask('')


@app.route('/')
def home():
  return 'Le bot est en ligne !'


def run():
  port = int(os.environ.get('PORT', 8080))
  app.run(host='0.0.0.0', port=port)


def keep_alive():
  t = Thread(target=run)
  t.start()


keep_alive()
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import chat_exporter
import io
import time
import random
import json
import os
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURATION GLOBALE & SÉCURITÉ
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN", "METS_TON_NOUVEAU_TOKEN_ICI")

# Identifiants des Rôles (NØVA RP)
ROLES_STAFF_IDS = [1537442543900299304]
ROLE_FONDATION_ID = 1537442501399679047
ROLE_CITOYENS_ID = 1537442570068688946

# Rôles Factions / Métiers RP
ROLE_LSPD_ID = 0
ROLE_EMS_ID = 0
ROLE_MECANO_ID = 0
ROLE_GANG_LEADER_ID = 0

# Salons de Logging & Alertes
LOG_CHANNEL_NAME = "logs-tickets"
SERVICE_LOG_CHANNEL = "logs-services"
MOD_LOG_CHANNEL = "logs-moderation"
ECONOMY_LOG_CHANNEL = "logs-economie"
LSPD_DISPATCH_CHANNEL = "dispatch-lspd"
ILLEGAL_LOG_CHANNEL = "logs-illegal"
TICKET_CATEGORY_NAME = "🎫 TICKETS"
RP_SERVICE_LOG = "logs-services-rp"

# Visuels & Charte Graphique
LOGO_URL = "https://cdn.discordapp.com/attachments/117c4aa4-cd0a-45d6-bad9-8d300327d21b.png"
COLOR_PRIMARY = discord.Color.from_rgb(88, 101, 242)
COLOR_SUCCESS = discord.Color.from_rgb(46, 204, 113)
COLOR_DANGER = discord.Color.from_rgb(231, 76, 60)
COLOR_GOLD = discord.Color.from_rgb(241, 196, 15)
COLOR_INFO = discord.Color.from_rgb(52, 152, 219)
COLOR_DARK = discord.Color.from_rgb(47, 49, 54)
COLOR_PURPLE = discord.Color.from_rgb(155, 89, 182)

# Configuration des Intents Discord
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# 2. PERSISTANCE DES DONNÉES (JSON DB)
# ==========================================

DATA_FILE = "nova_rp_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "economy": {},
            "inventories": {},
            "warns": {},
            "records": {},
            "staff_hours": {},
            "xp": {},
            "vehicles": {},
            "gangs": {},
            "licenses": {},
            "fines": {},
            "blackmarket": {},
            "rp_services": {},
            "properties": {},
            "ads": []
        }
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Erreur lors du chargement des données : {e}")
        return {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4, ensure_ascii=False)

db = load_data()
active_services = {}
active_rp_services = {}

def check_user_db(user_id: str):
    user_id = str(user_id)
    keys = ["economy", "inventories", "warns", "records", "staff_hours", "xp", "vehicles", "licenses", "fines", "blackmarket", "rp_services", "properties"]
    for key in keys:
        if key not in db:
            db[key] = {}

    if user_id not in db["economy"]:
        db["economy"][user_id] = {"wallet": 500, "bank": 2500, "daily_cooldown": 0, "rob_cooldown": 0, "work_cooldown": 0, "harvest_cooldown": 0}
    if user_id not in db["inventories"]:
        db["inventories"][user_id] = {}
    if user_id not in db["warns"]:
        db["warns"][user_id] = []
    if user_id not in db["records"]:
        db["records"][user_id] = []
    if user_id not in db["xp"]:
        db["xp"][user_id] = {"xp": 0, "level": 1}
    if user_id not in db["vehicles"]:
        db["vehicles"][user_id] = []
    if user_id not in db["licenses"]:
        db["licenses"][user_id] = {"drive": True, "weapon": False, "fly": False}
    if user_id not in db["fines"]:
        db["fines"][user_id] = []
    if user_id not in db["blackmarket"]:
        db["blackmarket"][user_id] = {"coke": 0, "weed": 0, "meth": 0}
    if user_id not in db["rp_services"]:
        db["rp_services"][user_id] = 0
    if user_id not in db["properties"]:
        db["properties"][user_id] = []

    save_data()

def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"

# ==========================================
# 3. INTERFACES POINTEUSE STAFF & RP
# ==========================================

def build_service_embed():
    embed = discord.Embed(
        title="⏱️ NØVA RP • Espace Prise de Service Staff",
        description=(
            "Bienvenue sur l'interface de pointeuse du Staff NØVA RP.\n\n"
            "🟢 **Prise de Service :** Débute ton temps de modération.\n"
            "🟠 **Pause / Reprise :** Mets en pause ton compteur si tu t'absentes.\n"
            "🔴 **Fin de Service :** Valide et enregistre ton temps effectué.\n\n"
            "⚠️ *Au bout de 24h consécutives, le service est automatiquement clôturé.*"
        ),
        color=COLOR_PRIMARY
    )
    embed.set_thumbnail(url=LOGO_URL)

    if not active_services:
        embed.add_field(
            name="📊 Membres actuellement en service (0)",
            value="*Aucun staff en service pour le moment.*",
            inline=False
        )
    else:
        now = time.time()
        lines = []
        for user_id, srv in active_services.items():
            status_icon = "🟠 (En Pause)" if srv["on_pause"] else "🟢 (En Service)"
            if srv["on_pause"]:
                elapsed = (srv["pause_start"] - srv["start_time"]) - srv["total_pause"]
            else:
                elapsed = (now - srv["start_time"]) - srv["total_pause"]
            lines.append(f"• <@{user_id}> {status_icon} — temps : `{format_duration(elapsed)}`")

        embed.add_field(
            name=f"📊 Membres actuellement en service ({len(active_services)})",
            value="\n".join(lines),
            inline=False
        )
    embed.set_footer(text="Système de pointeuse NØVA RP", icon_url=LOGO_URL)
    return embed

class ServiceControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Prise de Service", style=discord.ButtonStyle.success, emoji="🟢", custom_id="service_start")
    async def start_service(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id in active_services:
            return await interaction.response.send_message("❌ Vous êtes déjà en service !", ephemeral=True)

        active_services[user_id] = {
            "start_time": time.time(),
            "pause_start": None,
            "total_pause": 0,
            "on_pause": False
        }

        embed_log = discord.Embed(
            title="🟢 Prise de Service Staff",
            description=f"{interaction.user.mention} a **pris son service** staff.",
            color=COLOR_SUCCESS,
            timestamp=datetime.now()
        )
        embed_log.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        log_chan = discord.utils.get(interaction.guild.text_channels, name=SERVICE_LOG_CHANNEL)
        if log_chan:
            await log_chan.send(embed=embed_log)

        await interaction.response.edit_message(embed=build_service_embed(), view=self)
        await interaction.followup.send("✅ Prise de service enregistrée.", ephemeral=True)

    @discord.ui.button(label="Pause / Reprise", style=discord.ButtonStyle.secondary, emoji="🟠", custom_id="service_pause")
    async def toggle_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id not in active_services:
            return await interaction.response.send_message("❌ Vous n'êtes pas en service.", ephemeral=True)

        srv = active_services[user_id]
        log_chan = discord.utils.get(interaction.guild.text_channels, name=SERVICE_LOG_CHANNEL)

        if not srv["on_pause"]:
            srv["on_pause"] = True
            srv["pause_start"] = time.time()
            msg = f"🟠 {interaction.user.mention} a mis son service **en pause**."
            status = "Pause enregistrée."
        else:
            srv["on_pause"] = False
            srv["total_pause"] += (time.time() - srv["pause_start"])
            srv["pause_start"] = None
            msg = f"▶️ {interaction.user.mention} a **repris** son service."
            status = "Reprise enregistrée."

        if log_chan:
            embed_log = discord.Embed(description=msg, color=COLOR_GOLD, timestamp=datetime.now())
            embed_log.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            await log_chan.send(embed=embed_log)

        await interaction.response.edit_message(embed=build_service_embed(), view=self)
        await interaction.followup.send(f"✅ {status}", ephemeral=True)

    @discord.ui.button(label="Fin de Service", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="service_stop")
    async def stop_service(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id not in active_services:
            return await interaction.response.send_message("❌ Vous n'êtes pas en service.", ephemeral=True)

        srv = active_services.pop(user_id)
        now = time.time()
        
        if srv["on_pause"]:
            srv["total_pause"] += (now - srv["pause_start"])

        gross_time = now - srv["start_time"]
        net_seconds = gross_time - srv["total_pause"]

        uid_str = str(user_id)
        check_user_db(uid_str)
        db["staff_hours"][uid_str] = db["staff_hours"].get(uid_str, 0) + net_seconds
        save_data()

        log_chan = discord.utils.get(interaction.guild.text_channels, name=SERVICE_LOG_CHANNEL)
        if log_chan:
            embed_log = discord.Embed(
                title="🔴 Fin de Service Staff",
                description=(
                    f"**Staff :** {interaction.user.mention}\n"
                    f"**Session :** `{format_duration(net_seconds)}`\n"
                    f"**Pause :** `{format_duration(srv['total_pause'])}`\n"
                    f"**Cumul Total :** `{format_duration(db['staff_hours'][uid_str])}`"
                ),
                color=COLOR_DANGER,
                timestamp=datetime.now()
            )
            embed_log.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            await log_chan.send(embed=embed_log)

        await interaction.response.edit_message(embed=build_service_embed(), view=self)
        await interaction.followup.send(f"✅ Service terminé (`{format_duration(net_seconds)}`).", ephemeral=True)

class RPServiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Prise de Service RP", style=discord.ButtonStyle.success, emoji="🚔", custom_id="rp_service_start")
    async def start_rp(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid in active_rp_services:
            return await interaction.response.send_message("❌ Vous êtes déjà en service RP.", ephemeral=True)
        
        active_rp_services[uid] = time.time()
        await interaction.response.send_message("🟢 Vous avez pris votre service RP !", ephemeral=True)

        log_chan = discord.utils.get(interaction.guild.text_channels, name=RP_SERVICE_LOG)
        if log_chan:
            embed = discord.Embed(title="🏢 Prise de Service Entreprise", description=f"{interaction.user.mention} a pris sa garde RP.", color=COLOR_SUCCESS)
            await log_chan.send(embed=embed)

    @discord.ui.button(label="Fin de Service RP", style=discord.ButtonStyle.danger, emoji="📻", custom_id="rp_service_stop")
    async def stop_rp(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid not in active_rp_services:
            return await interaction.response.send_message("❌ Vous n'êtes pas en service RP.", ephemeral=True)

        start = active_rp_services.pop(uid)
        duration = time.time() - start
        
        uid_str = str(uid)
        check_user_db(uid_str)
        db["rp_services"][uid_str] = db["rp_services"].get(uid_str, 0) + duration
        save_data()

        await interaction.response.send_message(f"🔴 Fin de service RP. Temps effectué : `{format_duration(duration)}`.", ephemeral=True)

        log_chan = discord.utils.get(interaction.guild.text_channels, name=RP_SERVICE_LOG)
        if log_chan:
            embed = discord.Embed(title="🏢 Fin de Service Entreprise", description=f"{interaction.user.mention} a quitté sa garde RP.\nSession : `{format_duration(duration)}`", color=COLOR_DANGER)
            await log_chan.send(embed=embed)

# ==========================================
# 4. TICKETS SYSTEM V2
# ==========================================

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="✋", custom_id="claim_ticket")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        allowed = ROLES_STAFF_IDS + ([ROLE_FONDATION_ID] if ROLE_FONDATION_ID != 0 else [])
        if not any(r.id in allowed for r in interaction.user.roles) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Réservé au staff.", ephemeral=True)
        
        button.disabled = True
        button.label = f"Pris par {interaction.user.display_name}"
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"📌 Ticket pris en charge par {interaction.user.mention}.")

    @discord.ui.button(label="Fermer", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_ticket")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Génération du transcript et fermeture...")
        try:
            transcript_html = await chat_exporter.export(interaction.channel)
            if transcript_html:
                transcript_bytes = io.BytesIO(transcript_html.encode("utf-8"))
                file = discord.File(transcript_bytes, filename=f"{interaction.channel.name}-transcript.html")
                log_chan = discord.utils.get(interaction.guild.text_channels, name=LOG_CHANNEL_NAME)
                if log_chan:
                    await log_chan.send(content=f"📜 Transcript du ticket `{interaction.channel.name}` :", file=file)
        except Exception as e:
            print(f"Erreur transcript : {e}")

        await asyncio.sleep(3)
        await interaction.channel.delete()

class TicketCreationModal(discord.ui.Modal):
    def __init__(self, cat):
        super().__init__(title=f"Ouverture Ticket - {cat}")
        self.cat = cat

    subject = discord.ui.TextInput(label="Sujet du ticket", min_length=3, placeholder="Ex: Remboursement RP / Bug")
    details = discord.ui.TextInput(label="Explications détaillées", style=discord.TextStyle.paragraph, min_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME) or await guild.create_category(TICKET_CATEGORY_NAME)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        for role_id in ROLES_STAFF_IDS:
            role = guild.get_role(role_id)
            if role: overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        chan = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )
        
        embed = discord.Embed(
            title=f"🎫 {self.subject.value}",
            description=f"**Demandeur :** {interaction.user.mention}\n**Catégorie :** {self.cat}\n\n```{self.details.value}```",
            color=COLOR_PRIMARY,
            timestamp=datetime.now()
        )
        embed.set_footer(text="NØVA RP • Support Staff", icon_url=LOGO_URL)
        
        await chan.send(content=f"{interaction.user.mention} | Un membre du Staff va prendre votre ticket.", embed=embed, view=TicketControlView())
        await interaction.response.send_message(f"✅ Ticket ouvert : {chan.mention}", ephemeral=True)

class TicketSelect(discord.ui.Select):
    def __init__(self):
        opts = [
            discord.SelectOption(label="Création d'entreprise", emoji="💼", description="Projet d'entreprise RP ou Faction"),
            discord.SelectOption(label="Signaler un Joueur / Bug", emoji="🐛", description="Problème technique ou non-respect du RP"),
            discord.SelectOption(label="Plainte Staff", emoji="🛡️", description="Contacter la haute direction"),
            discord.SelectOption(label="Demande de Douane / WL", emoji="🛂", description="Accès au serveur RP"),
            discord.SelectOption(label="Autre demande", emoji="❓", description="Question générale")
        ]
        super().__init__(placeholder="Motif du ticket...", options=opts, custom_id="ticket_select_menu")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketCreationModal(self.values[0]))

class TicketMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

# ==========================================
# 5. SESSIONS RP & LEBONCOIN RP
# ==========================================

class AdModal(discord.ui.Modal, title="📢 Petite Annonce Leboncoin RP"):
    title_ad = discord.ui.TextInput(label="Titre de l'annonce", min_length=5)
    price = discord.ui.TextInput(label="Prix demandé ($)", placeholder="Ex: 15000")
    desc = discord.ui.TextInput(label="Description du bien / service", style=discord.TextStyle.paragraph, min_length=10)
    contact = discord.ui.TextInput(label="Numéro Téléphone / Contact RP", placeholder="Ex: 555-0192")

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"🏷️ ANNONCE : {self.title_ad.value.upper()}",
            description=(
                f"**Prix :** `{self.price.value}$`\n"
                f"**Vendeur :** {interaction.user.mention}\n"
                f"**Contact RP :** `{self.contact.value}`\n\n"
                f"**Description :**\n```{self.desc.value}```"
            ),
            color=COLOR_GOLD,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="NØVA RP • Petites Annonces Citizens")

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Votre annonce a été publiée !", ephemeral=True)

# ==========================================
# 6. ÉCONOMIE, INVENTAIRE & BOUTIQUE
# ==========================================

class ShopSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Téléphone RP", value="phone", description="Prix: 500$", emoji="📱"),
            discord.SelectOption(label="Kit de Soin", value="medkit", description="Prix: 300$", emoji="🩹"),
            discord.SelectOption(label="Kevlar LSPD", value="kevlar", description="Prix: 1200$", emoji="🛡️"),
            discord.SelectOption(label="Menottes", value="cuffs", description="Prix: 450$", emoji="🔗"),
            discord.SelectOption(label="Burger & Eau", value="food", description="Prix: 50$", emoji="🍔"),
            discord.SelectOption(label="Crochet de Serrure", value="lockpick", description="Prix: 800$", emoji="🗝️")
        ]
        super().__init__(placeholder="Sélectionner un produit...", options=options)

    async def callback(self, interaction: discord.Interaction):
        item = self.values[0]
        prices = {"phone": 500, "medkit": 300, "kevlar": 1200, "cuffs": 450, "food": 50, "lockpick": 800}
        names = {"phone": "Téléphone RP", "medkit": "Kit de Soin", "kevlar": "Kevlar LSPD", "cuffs": "Menottes", "food": "Pack Nourriture", "lockpick": "Crochetage"}
        
        cost = prices[item]
        uid = str(interaction.user.id)
        check_user_db(uid)

        if db["economy"][uid]["wallet"] < cost:
            return await interaction.response.send_message(f"❌ Espèces insuffisantes ! Il faut `{cost}$`.", ephemeral=True)

        db["economy"][uid]["wallet"] -= cost
        item_name = names[item]
        db["inventories"][uid][item_name] = db["inventories"][uid].get(item_name, 0) + 1
        save_data()

        await interaction.response.send_message(f"🛒 Achat effectué : **1x {item_name}** (`{cost}$`).", ephemeral=True)

class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(ShopSelect())

# ==========================================
# 7. COMMANDES PRINCIPALES DU BOT
# ==========================================

@bot.event
async def on_ready():
    print(f"🤖 Bot connecté en tant que : {bot.user.name} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"⚡ Synchros des commandes Slash : {len(synced)} commandes actived.")
    except Exception as e:
        print(f"⚠️ Erreur de sync Slash Commands : {e}")

# --- GESTION SERVICES STAFF & SETUP ---

@bot.command()
@commands.has_permissions(administrator=True)
async def service_setup(ctx):
    await ctx.message.delete()
    await ctx.send(embed=build_service_embed(), view=ServiceControlView())

@bot.command()
@commands.has_permissions(administrator=True)
async def rp_service_setup(ctx):
    await ctx.message.delete()
    embed = discord.Embed(
        title="🏢 NØVA RP • Pointeuse Entreprises & Services Publics",
        description="Prenez votre garde LSPD, EMS, Mécano ou entreprise privée ci-dessous.",
        color=COLOR_PRIMARY
    )
    await ctx.send(embed=embed, view=RPServiceView())

@bot.command()
@commands.has_permissions(administrator=True)
async def ticket_setup(ctx):
    await ctx.message.delete()
    embed = discord.Embed(
        title="✨ NØVA RP • Centre d'Assistance & Support",
        description="Besoin d'aide ou d'un renseignement ? Ouvrez un ticket ci-dessous.",
        color=COLOR_PRIMARY
    )
    embed.set_thumbnail(url=LOGO_URL)
    await ctx.send(embed=embed, view=TicketMainView())

# COMMANDE SESSION CORRIGÉE (ENVOI DIRECT)
@bot.command()
@commands.has_permissions(administrator=True)
async def session(ctx):
    await ctx.message.delete()
    role_citoyen = ctx.guild.get_role(ROLE_CITOYENS_ID)
    ping_str = role_citoyen.mention if role_citoyen else "@everyone"

    embed = discord.Embed(
        title="🚨 NØVA RP • LA SESSION EST OUVERTE !",
        description=(
            f"La session RP sur **NØVA RP (Roblox)** vient officiellement de lancer ses portes !\n\n"
            f"📌 **Message de la Direction :**\n"
            f"La session Nova RP est ouverte ! Rejoignez le serveur dès maintenant pour lancer vos scènes RP !\n\n"
            f"🎮 **Serveur Roblox :** Connectez-vous via l'accès au jeu.\n"
            f"⚠️ **Rappel :** Respectez scrupuleusement le règlement de la ville en scène."
        ),
        color=COLOR_SUCCESS,
        timestamp=datetime.now()
    )
    embed.set_thumbnail(url=LOGO_URL)
    embed.set_footer(text="NØVA RP • Bon jeu à tous !", icon_url=LOGO_URL)

    await ctx.send(content=f"🔔 {ping_str}", embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def annonce(ctx, *, message: str):
    await ctx.message.delete()
    embed = discord.Embed(
        title="📢 ANNONCE OFFICIELLE NØVA RP",
        description=message,
        color=COLOR_PRIMARY,
        timestamp=datetime.now()
    )
    embed.set_footer(text=f"Publication par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def staff_leaderboard(ctx):
    embed = discord.Embed(title="📊 Classement du Temps Staff NØVA RP", color=COLOR_GOLD)
    if not db.get("staff_hours"):
        embed.description = "Aucune donnée enregistrée."
    else:
        sorted_staff = sorted(db["staff_hours"].items(), key=lambda x: x[1], reverse=True)
        txt = ""
        for i, (u_id, sec) in enumerate(sorted_staff[:10], 1):
            user = bot.get_user(int(u_id))
            name = user.display_name if user else f"ID: {u_id}"
            txt += f"**#{i} {name}** — `{format_duration(sec)}`\n"
        embed.description = txt
    await ctx.send(embed=embed)

# --- COMMANDES D'ADMINISTRATION ÉCONOMIE ---

@bot.command()
@commands.has_permissions(administrator=True)
async def addmoney(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        return await ctx.send("❌ Le montant doit être supérieur à 0.")
    
    uid = str(member.id)
    check_user_db(uid)

    db["economy"][uid]["bank"] += amount
    save_data()

    embed = discord.Embed(
        title="🏦 Injection Bancaire Administration",
        description=f"✅ `{amount}$` ont été ajoutés sur le compte bancaire de {member.mention}.",
        color=COLOR_SUCCESS
    )
    await ctx.send(embed=embed)

# --- SYSTEME ÉCONOMIQUE, BRAQUAGES & ILLÉGAL ---

@bot.command()
async def money(ctx, member: discord.Member = None):
    target = member or ctx.author
    uid = str(target.id)
    check_user_db(uid)

    wallet = db["economy"][uid]["wallet"]
    bank = db["economy"][uid]["bank"]

    embed = discord.Embed(title=f"💳 Compte & Portefeuille • {target.display_name}", color=COLOR_SUCCESS)
    embed.add_field(name="💵 Espèces", value=f"`{wallet}$`", inline=True)
    embed.add_field(name="🏦 Banque", value=f"`{bank}$`", inline=True)
    embed.add_field(name="💰 Total", value=f"`{wallet + bank}$`", inline=False)
    embed.set_thumbnail(url=target.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command()
async def work(ctx):
    uid = str(ctx.author.id)
    check_user_db(uid)

    now = time.time()
    last = db["economy"][uid].get("work_cooldown", 0)
    if now - last < 3600:
        remaining = 3600 - (now - last)
        return await ctx.send(f"⏱️ Reposez-vous ! Prochain service dans `{int(remaining // 60)} minutes`.")

    salary = random.randint(250, 600)
    db["economy"][uid]["wallet"] += salary
    db["economy"][uid]["work_cooldown"] = now
    save_data()

    jobs = ["un service de livraison", "un tour de garde LSPD", "une réparation mécano", "un nettoyage de la ville"]
    await ctx.send(f"💼 **{ctx.author.display_name}** a effectué {random.choice(jobs)} et gagne `{salary}$` en liquide !")

@bot.command()
async def daily(ctx):
    uid = str(ctx.author.id)
    check_user_db(uid)

    now = time.time()
    last = db["economy"][uid]["daily_cooldown"]
    
    if now - last < 86400:
        remaining = 86400 - (now - last)
        return await ctx.send(f"⏱️ Bonus indisponible. Attendez `{format_duration(remaining)}`.")

    db["economy"][uid]["bank"] += 1200
    db["economy"][uid]["daily_cooldown"] = now
    save_data()

    await ctx.send("🎁 Vous avez reçu votre bonus quotidien de **1200$** sur votre compte en banque !")

@bot.command()
async def deposit(ctx, amount: int):
    if amount <= 0: return await ctx.send("❌ Montant invalide.")
    uid = str(ctx.author.id)
    check_user_db(uid)

    if db["economy"][uid]["wallet"] < amount:
        return await ctx.send("❌ Vous n'avez pas cette somme sur vous.")

    db["economy"][uid]["wallet"] -= amount
    db["economy"][uid]["bank"] += amount
    save_data()
    await ctx.send(f"🏦 Vous avez déposé `{amount}$` à la banque.")

@bot.command()
async def withdraw(ctx, amount: int):
    if amount <= 0: return await ctx.send("❌ Montant invalide.")
    uid = str(ctx.author.id)
    check_user_db(uid)

    if db["economy"][uid]["bank"] < amount:
        return await ctx.send("❌ Vous n'avez pas cette somme en banque.")

    db["economy"][uid]["bank"] -= amount
    db["economy"][uid]["wallet"] += amount
    save_data()
    await ctx.send(f"🏧 Vous avez retiré `{amount}$` du distributeur.")

@bot.command()
async def rob(ctx, member: discord.Member):
    if member.id == ctx.author.id: return await ctx.send("❌ Vous ne pouvez pas vous volé vous-même.")
    
    attacker_id = str(ctx.author.id)
    victim_id = str(member.id)
    check_user_db(attacker_id)
    check_user_db(victim_id)

    now = time.time()
    last = db["economy"][attacker_id].get("rob_cooldown", 0)
    if now - last < 7200:
        return await ctx.send(f"⏱️ Attendez encore `{int((7200 - (now - last)) // 60)} minutes` avant de rebraquer.")

    victim_wallet = db["economy"][victim_id]["wallet"]
    if victim_wallet < 200:
        return await ctx.send(f"❌ **{member.display_name}** n'a pas assez d'espèces sur lui.")

    success = random.choice([True, False, False]) # 33% de chance
    db["economy"][attacker_id]["rob_cooldown"] = now

    if success:
        stolen = random.randint(100, victim_wallet)
        db["economy"][victim_id]["wallet"] -= stolen
        db["economy"][attacker_id]["wallet"] += stolen
        save_data()
        await ctx.send(f"🥷 **{ctx.author.display_name}** a dépouillé **{member.display_name}** et repart avec `{stolen}$` !")
    else:
        fine = 300
        db["economy"][attacker_id]["wallet"] = max(0, db["economy"][attacker_id]["wallet"] - fine)
        save_data()
        await ctx.send(f"🚨 **{ctx.author.display_name}** a raté son agression ! La police intervient et lui fait payer `{fine}$` d'amende.")

@bot.command()
async def rob_store(ctx):
    uid = str(ctx.author.id)
    check_user_db(uid)

    if "Crochetage" not in db["inventories"][uid] or db["inventories"][uid]["Crochetage"] <= 0:
        return await ctx.send("❌ Il vous faut un **Crochet de Serrure** (disponible au `!shop`) pour tenter un braquage.")

    db["inventories"][uid]["Crochetage"] -= 1
    
    # Alerte LSPD Dispatch
    dispatch = discord.utils.get(ctx.guild.text_channels, name=LSPD_DISPATCH_CHANNEL)
    if dispatch:
        embed_alt = discord.Embed(
            title="🚨 ALERTE BRAQUAGE DE SUPÉRETTE",
            description=f"Un braquage de supérette est en cours au secteur **{ctx.channel.name}** !",
            color=COLOR_DANGER
        )
        await dispatch.send(content="@here 🚔 **LSPD DISPATCH**", embed=embed_alt)

    await ctx.send("🛠️ Tentative de crochetage de la caisse enregistreuse en cours... (Patientez 5 sec)")
    await asyncio.sleep(5)

    if random.choice([True, False]):
        loot = random.randint(1500, 4500)
        db["economy"][uid]["wallet"] += loot
        save_data()
        await ctx.send(f"💰 Braquage réussi ! Vous avez extrait `{loot}$` du coffre !")
    else:
        await ctx.send("💥 Le crochet a cassé et l'alarme silencieuse s'est déclenchée ! Fuite recommandée !")

@bot.command()
async def pay(ctx, member: discord.Member, amount: int):
    if amount <= 0: return await ctx.send("❌ Montant invalide.")
    
    sender_id = str(ctx.author.id)
    recv_id = str(member.id)
    check_user_db(sender_id)
    check_user_db(recv_id)

    if db["economy"][sender_id]["wallet"] < amount:
        return await ctx.send("❌ Espèces insuffisantes.")

    db["economy"][sender_id]["wallet"] -= amount
    db["economy"][recv_id]["wallet"] += amount
    save_data()

    await ctx.send(f"💸 **{ctx.author.display_name}** a transféré `{amount}$` à **{member.display_name}**.")

@bot.command()
async def shop(ctx):
    embed = discord.Embed(title="🛒 Superette & Armurerie Légale", description="Achetez des équipements utiles à votre aventure RP :", color=COLOR_PRIMARY)
    await ctx.send(embed=embed, view=ShopView())

@bot.command()
async def inventory(ctx, member: discord.Member = None):
    target = member or ctx.author
    uid = str(target.id)
    check_user_db(uid)

    inv = db["inventories"].get(uid, {})
    embed = discord.Embed(title=f"🎒 Inventaire RP • {target.display_name}", color=COLOR_PRIMARY)
    
    if not inv or sum(inv.values()) == 0:
        embed.description = "*Votre sac à dos est vide.*"
    else:
        items_desc = []
        for item, count in inv.items():
            if count > 0:
                items_desc.append(f"• **{item}** : `{count}`")
        embed.description = "\n".join(items_desc) if items_desc else "*Votre sac à dos est vide.*"

    embed.set_thumbnail(url=target.display_avatar.url)
    await ctx.send(embed=embed)

# --- NOUVELLES COMMANDES AJOUTÉES (ILLÉGAL, IMMOBILIER & LSPD) ---

@bot.command()
async def harvest(ctx):
    """Commande pour le serveur Nova RP Illégal : Récolte de pochons"""
    uid = str(ctx.author.id)
    check_user_db(uid)

    now = time.time()
    last = db["economy"][uid].get("harvest_cooldown", 0)
    if now - last < 1800:
        remaining = 1800 - (now - last)
        return await ctx.send(f"⏱️ Zone surveillée ! Revenez dans `{int(remaining // 60)} minutes`.")

    gathered = random.randint(2, 6)
    db["blackmarket"][uid]["weed"] = db["blackmarket"][uid].get("weed", 0) + gathered
    db["economy"][uid]["harvest_cooldown"] = now
    save_data()

    await ctx.send(f"🌿 **{ctx.author.display_name}** a récolté `{gathered}x Pochons de Weed` en zone illégale.")

@bot.command()
async def sell_illegal(ctx):
    """Commande pour le serveur Nova RP Illégal : Revente au marché noir"""
    uid = str(ctx.author.id)
    check_user_db(uid)

    weed_count = db["blackmarket"][uid].get("weed", 0)
    if weed_count <= 0:
        return await ctx.send("❌ Vous n'avez aucune marchandise à revendre.")

    price_per_unit = random.randint(150, 300)
    total_gain = weed_count * price_per_unit

    db["blackmarket"][uid]["weed"] = 0
    db["economy"][uid]["wallet"] += total_gain
    save_data()

    await ctx.send(f"🏴‍☠️ Revente effectuée ! Vous avez écoulé `{weed_count} pochons` pour un total de `{total_gain}$` en liquide !")

@bot.command()
async def buy_house(ctx, house_name: str, price: int):
    """Commande pour le serveur Nova RP Immobilier : Achat de propriété"""
    if price <= 0:
        return await ctx.send("❌ Prix invalide.")
    
    uid = str(ctx.author.id)
    check_user_db(uid)

    if db["economy"][uid]["bank"] < price:
        return await ctx.send(f"❌ Fonds insuffisants en banque ! Il vous faut `{price}$`.")

    db["economy"][uid]["bank"] -= price
    db["properties"][uid].append({"name": house_name, "bought_at": price, "date": str(datetime.now().strftime("%Y-%m-%d"))})
    save_data()

    embed = discord.Embed(
        title="🏡 NØVA IMMOBILIER • Acte de Vente",
        description=f"Félicitations {ctx.author.mention} !\nVous êtes désormais propriétaire du bien : **{house_name}** pour `{price}$`.",
        color=COLOR_SUCCESS
    )
    await ctx.send(embed=embed)

@bot.command()
async def properties(ctx, member: discord.Member = None):
    """Commande pour le serveur Nova RP Immobilier : Consulter ses propriétés"""
    target = member or ctx.author
    uid = str(target.id)
    check_user_db(uid)

    props = db["properties"].get(uid, [])
    embed = discord.Embed(title=f"🏰 Patrimoine Immobilier • {target.display_name}", color=COLOR_GOLD)
    
    if not props:
        embed.description = "*Aucune propriété enregistrée.*"
    else:
        lines = [f"• **{p['name']}** (Acheté `{p['bought_at']}$` le {p['date']})" for p in props]
        embed.description = "\n".join(lines)

    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def fine(ctx, member: discord.Member, amount: int, *, reason: str = "Non-respect du code RP"):
    """Commande pour infliger une amende à un citoyen"""
    if amount <= 0:
        return await ctx.send("❌ Montant d'amende invalide.")

    uid = str(member.id)
    check_user_db(uid)

    db["economy"][uid]["bank"] = max(0, db["economy"][uid]["bank"] - amount)
    db["fines"][uid].append({"amount": amount, "reason": reason, "date": str(datetime.now().strftime("%Y-%m-%d %H:%M"))})
    save_data()

    embed = discord.Embed(
        title="⚖️ NØVA RP • Procès-Verbal d'Amende",
        description=(
            f"**Citoyen verbalisé :** {member.mention}\n"
            f"**Montant de l'amende :** `{amount}$` (Prélevé en banque)\n"
            f"**Motif :** `{reason}`\n"
            f"**Agent / Staff :** {ctx.author.mention}"
        ),
        color=COLOR_DANGER
    )
    await ctx.send(embed=embed)

# ==========================================
# 8. LANCEMENT DU BOT
# ==========================================

if __name__ == "__main__":
    if TOKEN == "METS_TON_NOUVEAU_TOKEN_ICI" or not TOKEN:
        print("❌ VEUILLEZ RENSEIGNER UN TOKEN DISCORD VALIDE DANS LE SCRIPT OU LA VARIABLE D'ENVIRONNEMENT.")
    else:
        bot.run(TOKEN)
