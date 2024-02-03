import json
import asyncio
import logging
from typing import cast

import discord
from discord.ext import commands

import wavelink


def load_config(filename: str) -> dict:
    """
    Load config from a .JSON file.
    """
    with open(filename) as file_object:
        config = json.load(file_object)
    return config


class Bot(commands.Bot):

    def __init__(self) -> None:
        self.config = load_config("config.json")
        intents: discord.Intents = discord.Intents.default()
        intents.message_content = True

        discord.utils.setup_logging(level=logging.INFO)
        super().__init__(command_prefix=self.config['PREFIX'], intents=intents)


    async def setup_hook(self) -> None:

        nodes = [wavelink.Node(uri=self.config['NODES'][0]['uri'], password=self.config['NODES'][0]['password'])]

        # cache_capacity is EXPERIMENTAL. Turn it off by passing None
        await wavelink.Pool.connect(nodes=nodes, client=self, cache_capacity=100)

    async def on_ready(self) -> None:
        logging.info(f"Logged in: {self.user} | {self.user.id}")

    async def on_wavelink_node_ready(
        self, payload: wavelink.NodeReadyEventPayload
    ) -> None:
        logging.info(
            f"Wavelink Node connected: {payload.node!r} | Resumed: {payload.resumed}"
        )

    async def on_wavelink_track_start(
        self, payload: wavelink.TrackStartEventPayload
    ) -> None:
        player: wavelink.Player | None = payload.player
        if not player:
            # Handle edge cases...
            return

        original: wavelink.Playable | None = payload.original
        track: wavelink.Playable = payload.track

        embed: discord.Embed = discord.Embed(title="Tocando agora...")
        embed.description = f"**{track.title}** de `{track.author}`"

        if track.artwork:
            embed.set_image(url=track.artwork)

        if original and original.recommended:
            embed.description += f"\n\n`Esta música foi recomendado por {track.source}`"

        if track.album.name:
            embed.add_field(name="Album", value=track.album.name)

        await player.home.send(embed=embed)


bot: Bot = Bot()


@bot.command(aliases=["p"])
async def play(ctx: commands.Context, *, query: str) -> None:
    """Play a song with the given query."""
    if not ctx.guild:
        return

    player: wavelink.Player
    player = cast(wavelink.Player, ctx.voice_client)  # type: ignore

    if not player:
        try:
            player = await ctx.author.voice.channel.connect(cls=wavelink.Player)  # type: ignore
        except AttributeError:
            await ctx.send(
                "Vou carregar música pra quem? ENTRA NO CANAL DISGRAÇA!"
            )
            return
        except discord.ClientException:
            await ctx.send("Está me vendo não? Eu já estou em um canal!")
            return

    # Turn on AutoPlay to enabled mode.
    # enabled = AutoPlay will play songs for us and fetch recommendations...
    # partial = AutoPlay will play songs for us, but WILL NOT fetch recommendations...
    # disabled = AutoPlay will do nothing...
    # implementar uma forma de desativar a recomendação
    player.autoplay = wavelink.AutoPlayMode.enabled

    # Lock the player to this channel...
    if not hasattr(player, "home"):
        player.home = ctx.channel
    elif player.home != ctx.channel:
        await ctx.send(
            f"Está achando que sou o naruto? Eu não consigo estar em dois lugares ao mesmo tempo!"
        )
        return

    # Search for the track...
    tracks: wavelink.Search = await wavelink.Playable.search(query)
    if not tracks:
        await ctx.send(
            f"{ctx.author.mention} - Escreve direito, sou vidente não fdp!"
        )
        return

    if isinstance(tracks, wavelink.Playlist):
        # tracks is a playlist...
        added: int = await player.queue.put_wait(tracks)
        await ctx.send(
            f"Adicionado a playlist **`{tracks.name}`** com **`{added}`** musicas na fila."
        )
    else:
        track: wavelink.Playable = tracks[0]
        await player.queue.put_wait(track)
        await ctx.send(f"Adicionado a musica **`{track}`** na fila")

    if not player.playing:
        # Play now since we aren't playing anything...
        await player.play(player.queue.get(), volume=100)

    # Optionally delete the invokers message...
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass


@bot.command()
async def skip(ctx: commands.Context) -> None:
    """Skip the current song."""
    player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
    if not player:
        return

    await player.skip(force=True)
    await ctx.message.reply("Eu carrego a musica e você pula, que injustiça!")


@bot.command()
async def nightcore(ctx: commands.Context) -> None:
    """Set the filter to a nightcore style."""
    player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
    if not player:
        return

    filters: wavelink.Filters = player.filters
    filters.timescale.set(pitch=1.2, speed=1.2, rate=1)
    await player.set_filters(filters)

    await ctx.message.reply("Aplicado o filtro Nightcore.")


@bot.command(name="toggle", aliases=["pause", "resume"])
async def pause_resume(ctx: commands.Context) -> None:
    """Pause or Resume the Player depending on its current state."""
    player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
    if not player:
        return

    await player.pause(not player.paused)
    await ctx.message.add_reaction("\u2705")


@bot.command()
async def volume(ctx: commands.Context, value: int) -> None:
    """Change the volume of the player."""
    player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
    if not player:
        return

    await player.set_volume(value)
    await ctx.message.reply(f"Ajustado para {value}% de volume.")


@bot.command(aliases=["dc", "stop"])
async def disconnect(ctx: commands.Context) -> None:
    """Disconnect the Player."""
    player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
    if not player:
        return

    await player.disconnect()
    await ctx.message.reply("Me usou agora me desconectou, isso é abuso!")


async def main() -> None:
    async with bot:
        await bot.start(bot.config["TOKEN"])


def run_bot():
    asyncio.run(main())
