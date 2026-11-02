"""Midseason rest-of-season (ROS) QB forecasting and trade-decision evaluation (D116).

Sub-modules, in dependency order:

* ``scoring``   -- configurable fantasy scoring from raw nflverse stat lines.
* ``snapshots`` -- leak-safe (season, snapshot-week, QB) panel built from the archived
                   FantasyPros ``ros-qb`` ECR snapshots plus nflverse results known *before* the
                   snapshot, with realized remaining-season points as the target.
* ``models``    -- Models A-E (ECR, production, usage/context, combined) behind one
                   fit/predict interface, fitted strictly on earlier seasons.
* ``metrics``   -- point accuracy, rank accuracy, pairwise accuracy, probability calibration,
                   decision regret, season-block bootstrap.
* ``backtest``  -- the walk-forward driver (``alpha-squad ros backtest``).
* ``lineup``    -- weekly optimal-lineup value and incremental trade value (Model F).
* ``trade``     -- trade-package evaluation + Monte Carlo on top of ``lineup``.

Everything here is research/decision tooling. It does not touch the draft engine, the
projection models, or any production table.
"""
