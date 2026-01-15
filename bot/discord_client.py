import discord
from discord.ext import commands

def build_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True  # IMPORTANT: activer Server Members Intent dans le Dev Portal

    bot = commands.Bot(command_prefix="!", intents=intents)
    return bot
