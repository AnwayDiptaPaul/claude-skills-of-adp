# -*- coding: utf-8 -*-
"""
structural_recognition_tools.py — MCP tool wrappers for the routes in
structural_recognition_routes.py.

WHERE THIS FILE GOES: copy it to
    <your clone of mcp-server-for-revit-python>/tools/structural_recognition_tools.py

Then wire it up (Part 3 of the repo's documented extension pattern — two small
edits, not covered by this file itself):

1. In revit-mcp-python.extension/startup.py, inside register_routes():
       from revit_mcp.structural_recognition import register_structural_recognition_routes
       register_structural_recognition_routes(api)

2. In tools/__init__.py, inside register_tools():
       from .structural_recognition_tools import register_structural_recognition_tools
       register_structural_recognition_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)

Restart pyRevit (Extensions may need a reload) and restart your MCP client
afterward so it picks up the six new tools below.
"""
from mcp.server.fastmcp import Context
from .utils import format_response


def register_structural_recognition_tools(mcp, revit_get, revit_post, revit_image=None):

    @mcp.tool()
    async def list_structural_columns(ctx: Context) -> str:
        """
        Returns every structural column in the active Revit model: family/type,
        material, level, insertion point, bounding-box vertical extent, and every
        Revit parameter on the element. Coordinates are in millimetres.
        """
        response = await revit_get("/structural_columns/", ctx)
        return format_response(response)

    @mcp.tool()
    async def list_structural_framing(ctx: Context) -> str:
        """
        Returns every structural framing element (beams, girders, braces) in the
        active Revit model: family/type, material, level, start/end curve, and
        every Revit parameter. Coordinates are in millimetres.
        """
        response = await revit_get("/structural_framing/", ctx)
        return format_response(response)

    @mcp.tool()
    async def list_walls(ctx: Context) -> str:
        """
        Returns every wall in the active Revit model: wall type, compound-structure
        material layers, overall width, level, start/end curve, and every Revit
        parameter (including Function, when set, which is the strongest available
        signal for shear/retaining/partition classification). Coordinates in mm.
        """
        response = await revit_get("/walls/", ctx)
        return format_response(response)

    @mcp.tool()
    async def list_floors(ctx: Context) -> str:
        """
        Returns every floor/slab in the active Revit model: floor type, material
        layers, total thickness, level, and every Revit parameter. mm units.
        """
        response = await revit_get("/floors/", ctx)
        return format_response(response)

    @mcp.tool()
    async def list_structural_foundations(ctx: Context) -> str:
        """
        Returns every structural foundation element (isolated/wall footings, pile
        caps, and piles — Revit doesn't separate piles into their own category, so
        this tool splits them by a family-name heuristic; see the route's docstring)
        in the active Revit model, with the same field set as the other list_*
        tools. mm units.
        """
        response = await revit_get("/structural_foundations/", ctx)
        return format_response(response)

    @mcp.tool()
    async def list_grids(ctx: Context) -> str:
        """
        Returns every grid line in the active Revit model: name/tag and start/end
        points in millimetres. Use alongside list_levels (already built into this
        server) to resolve every other element's grid_ref and story.
        """
        response = await revit_get("/grids/", ctx)
        return format_response(response)

    return mcp
