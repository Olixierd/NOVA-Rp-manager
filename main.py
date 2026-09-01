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

# Récupération du token (Met ton nouveau token via variable ou directement)
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
    keys = ["economy", "inventories", "warns", "records", "staff_hours", "xp", "vehicles", "licenses", "fines", "blackmarket", "rp_services"]
    for key in keys:
        if key not in db:
            db[key] = {}

    if user_id not in db["economy"]:
        db["economy"][user_id] = {"wallet": 500, "bank": 2500, "daily_cooldown": 0, "rob_cooldown": 0, "work_cooldown": 0}
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

# POINTEUSE RP (ENTREPRISES RP : LSPD, EMS, MÉCANO)

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

class SessionModal(discord.ui.Modal, title="📢 Lancer une Session RP"):
    lieu = discord.ui.TextInput(label="Lieu de Rassemblement", default="Concessionnaire Principal", min_length=2)
    theme = discord.ui.TextInput(label="Thème / Type de RP", default="Session RP Ouverte", min_length=2)
    notes = discord.ui.TextInput(
        label="Consignes & Détails",
        style=discord.TextStyle.paragraph,
        default="🔥 Rejoignez-nous pour une session RP inédite sur NØVA RP !",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        role_citoyen = interaction.guild.get_role(ROLE_CITOYENS_ID)
        ping_str = role_citoyen.mention if role_citoyen else "@everyone"

        embed = discord.Embed(
            title="🚀 NØVA RP • SESSION RP OUVERTE !",
            description=(
                f"La ville de **NØVA RP** ouvre officiellement ses portes !\n\n"
                f"────────── **INFORMATIONS SESSION** ──────────\n"
                f"📍 **Lieu de rendez-vous :** `{self.lieu.value}`\n"
                f"🎭 **Thème :** `{self.theme.value}`\n"
                f"⏰ **Statut :** `En Cours`\n\n"
                f"────────── **CONSIGNES & INFORMATIONS** ──────────\n"
                f"```{self.notes.value}```"
            ),
            color=COLOR_SUCCESS,
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=LOGO_URL)
        embed.set_footer(text="NØVA RP • Bon jeu à tous !", icon_url=LOGO_URL)

        await interaction.channel.send(content=f"🔔 {ping_str}", embed=embed)
        await interaction.response.send_message("✅ Annonce publiée avec succès !", ephemeral=True)

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

@bot.command()
@commands.has_permissions(administrator=True)
async def session(ctx):
    await ctx.message.delete()
    await ctx.send_modal(SessionModal())

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
async def inventory(ctx):
    uid = str(ctx.author.id)
    check_user_db(uid)

    inv = db["inventories"][uid]
    embed = discord.Embed(title=f"🎒 Inventaire RP • {ctx.author.display_name}", color=COLOR_GOLD)

    if not inv:
        embed.description = "*Votre sac est totalement vide.*"
    else:
        lines = [f"• **{item}** x`{qty}`" for item, qty in inv.items() if qty > 0]
        embed.description = "\n".join(lines) if lines else "*Votre sac est totalement vide.*"

    await ctx.send(embed=embed)

# --- PERMIS, LICENCES & CASIER LSPD ---

@bot.command()
async def licenses(ctx, member: discord.Member = None):
    target = member or ctx.author
    uid = str(target.id)
    check_user_db(uid)

    lic = db["licenses"][uid]
    embed = discord.Embed(title=f"🪪 Licences & Permis • {target.display_name}", color=COLOR_INFO)
    embed.add_field(name="🚗 Permis de Conduire", value="✅ Valide" if lic.get("drive") else "❌ Suspendu/Non possédé", inline=False)
    embed.add_field(name="🔫 Permis Port d'Armes (PPA)", value="✅ Valide" if lic.get("weapon") else "❌ Non possédé", inline=False)
    embed.add_field(name="✈️ Licence de Vol", value="✅ Valide" if lic.get("fly") else "❌ Non possédée", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(kick_members=True)
async def give_license(ctx, member: discord.Member, lic_type: str):
    lic_type = lic_type.lower()
    if lic_type not in ["drive", "weapon", "fly"]:
        return await ctx.send("❌ Type invalide. Choix : `drive`, `weapon`, `fly`")

    uid = str(member.id)
    check_user_db(uid)
    db["licenses"][uid][lic_type] = True
    save_data()
    await ctx.send(f"✅ Licence `{lic_type}` accordée à **{member.display_name}**.")

@bot.command()
@commands.has_permissions(kick_members=True)
async def revoke_license(ctx, member: discord.Member, lic_type: str):
    lic_type = lic_type.lower()
    if lic_type not in ["drive", "weapon", "fly"]:
        return await ctx.send("❌ Type invalide. Choix : `drive`, `weapon`, `fly`")

    uid = str(member.id)
    check_user_db(uid)
    db["licenses"][uid][lic_type] = False
    save_data()
    await ctx.send(f"⚠️ Licence `{lic_type}` retirée à **{member.display_name}**.")

@bot.command()
@commands.has_permissions(kick_members=True)
async def add_fine(ctx, member: discord.Member, amount: int, *, reason: str):
    uid = str(member.id)
    check_user_db(uid)

    db["fines"][uid].append({"amount": amount, "reason": reason, "date": datetime.now().strftime("%d/%m/%Y")})
    save_data()

    embed = discord.Embed(title="📜 Nouvelle Amende LSPD", color=COLOR_DANGER)
    embed.add_field(name="Contrevenant", value=member.mention)
    embed.add_field(name="Montant", value=f"`{amount}$`")
    embed.add_field(name="Motif", value=reason)
    embed.set_footer(text=f"Agent : {ctx.author.display_name}")
    await ctx.send(embed=embed)

@bot.command()
async def fines(ctx):
    uid = str(ctx.author.id)
    check_user_db(uid)

    user_fines = db["fines"][uid]
    embed = discord.Embed(title=f"🧾 Vos Amendes Impayées", color=COLOR_DANGER)

    if not user_fines:
        embed.description = "*Vous n'avez aucune amende en attente.*"
    else:
        total = sum(f["amount"] for f in user_fines)
        txt = ""
        for i, f in enumerate(user_fines, 1):
            txt += f"**#{i}** `{f['amount']}$` — {f['reason']} ({f['date']})\n"
        embed.description = txt
        embed.add_field(name="Total à régler", value=f"`{total}$` (`!pay_fines` pour tout régler)")

    await ctx.send(embed=embed)

@bot.command()
async def pay_fines(ctx):
    uid = str(ctx.author.id)
    check_user_db(uid)

    user_fines = db["fines"][uid]
    if not user_fines:
        return await ctx.send("❌ Vous n'avez aucune amende à payer.")

    total = sum(f["amount"] for f in user_fines)
    if db["economy"][uid]["bank"] < total:
        return await ctx.send(f"❌ Fonds insuffisants en banque pour régler les `{total}$` d'amendes.")

    db["economy"][uid]["bank"] -= total
    db["fines"][uid] = []
    save_data()
    await ctx.send(f"✅ Toutes vos amendes (`{total}$`) ont été réglées par virement bancaire.")

# --- VÉHICULES & ANNONCES CITOYENNES ---

@bot.command()
async def buy_vehicle(ctx, model: str):
    prices = {"zentorno": 150000, "sultan": 45000, "panto": 10000, "baller": 65000, "t20": 250000, "sanchez": 20000}
    model = model.lower()

    if model not in prices:
        return await ctx.send(f"❌ Modèle non répertorié. Choix : `{', '.join(prices.keys())}`")

    cost = prices[model]
    uid = str(ctx.author.id)
    check_user_db(uid)

    if db["economy"][uid]["bank"] < cost:
        return await ctx.send("❌ Fonds insuffisants en banque.")

    db["economy"][uid]["bank"] -= cost
    plate = f"NV-{random.randint(100, 999)}-RP"
    db["vehicles"][uid].append({"model": model.upper(), "plate": plate})
    save_data()

    await ctx.send(f"🚗 Véhicule **{model.upper()}** acheté avec succès ! Plaque immatriculée : `{plate}`.")

@bot.command()
async def garage(ctx):
    uid = str(ctx.author.id)
    check_user_db(uid)

    vehs = db["vehicles"][uid]
    embed = discord.Embed(title=f"🚘 Garage Personnel • {ctx.author.display_name}", color=COLOR_PRIMARY)
    if not vehs:
        embed.description = "*Aucun véhicule enregistré dans le garage.*"
    else:
        lines = [f"• **{v['model']}** — Plaque : `{v['plate']}`" for v in vehs]
        embed.description = "\n".join(lines)
    await ctx.send(embed=embed)

@bot.command()
async def leboncoin(ctx):
    await ctx.send_modal(AdModal())

# --- MODÉRATION AVANCÉE & ADMINISTRATION ---

@bot.command()
@commands.has_permissions(kick_members=True)
async def timeout(ctx, member: discord.Member, minutes: int, *, reason: str = "Aucune raison"):
    duration = timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await ctx.send(f"🔇 {member.mention} a été mis en sourdine pour **{minutes} minutes**. Raison : {reason}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("🔒 Le salon a été verrouillé par le staff.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("🔓 Le salon est de nouveau ouvert.")

@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason: str = "Aucune raison"):
    uid = str(member.id)
    check_user_db(uid)

    db["warns"][uid].append(reason)
    save_data()

    await ctx.send(f"⚠️ {member.mention} a reçu un avertissement : **{reason}** (Total : {len(db['warns'][uid])})")

@bot.command()
async def warnings(ctx, member: discord.Member):
    uid = str(member.id)
    check_user_db(uid)
    w = db["warns"][uid]

    embed = discord.Embed(title=f"⚠️ Avertissements de {member.display_name}", color=COLOR_GOLD)
    embed.description = "\n".join([f"• {r}" for r in w]) if w else "Aucun avertissement."
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int = 5):
    await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🧹 `{amount}` messages nettoyés.", delete_after=3)

# ==========================================
# 8. TÂCHES AUTOMATIQUES EN ARRIÈRE-PLAN
# ==========================================

@tasks.loop(minutes=5)
async def check_long_services():
    now = time.time()
    to_remove = []

    for user_id, srv in list(active_services.items()):
        if (now - srv["start_time"]) >= 86400:
            to_remove.append(user_id)

    for user_id in to_remove:
        srv = active_services.pop(user_id)
        net_seconds = (now - srv["start_time"]) - srv["total_pause"]
        
        uid_str = str(user_id)
        check_user_db(uid_str)
        db["staff_hours"][uid_str] = db["staff_hours"].get(uid_str, 0) + net_seconds
        save_data()

        for guild in bot.guilds:
            member = guild.get_member(user_id)
            log_chan = discord.utils.get(guild.text_channels, name=SERVICE_LOG_CHANNEL)
            if log_chan and member:
                embed = discord.Embed(
                    title="⚠️ Clôture Automatique (24h)",
                    description=f"Le service de {member.mention} a été arrêté automatiquement après **24h**.",
                    color=COLOR_DANGER
                )
                await log_chan.send(embed=embed)

# ==========================================
# 9. ÉVÉNEMENTS & INITIALISATION DU BOT
# ==========================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Progression d'XP par activité
    uid = str(message.author.id)
    check_user_db(uid)
    
    db["xp"][uid]["xp"] += random.randint(3, 10)
    needed_xp = db["xp"][uid]["level"] * 120
    
    if db["xp"][uid]["xp"] >= needed_xp:
        db["xp"][uid]["level"] += 1
        db["xp"][uid]["xp"] = 0
        save_data()

    await bot.process_commands(message)

@bot.event
async def on_ready():
    # Vues Persistantes (Ne se désactivent pas au redémarrage)
    bot.add_view(TicketMainView())
    bot.add_view(TicketControlView())
    bot.add_view(ServiceControlView())
    bot.add_view(RPServiceView())

    if not check_long_services.is_running():
        check_long_services.start()

    print(f"==========================================")
    print(f"🔥 NØVA RP Bot connecté avec succès !")
    print(f"🤖 Bot : {bot.user.name} (ID: {bot.user.id})")
    print(f"📁 Sauvegarde globale JSON synchronisée.")
    print(f"==========================================")

# Lancement du Bot
if __name__ == "__main__":
    bot.run("TOKEN")