"""Look at what the engine does.

    make viz                  # the studio: five chapters over one position
    make viz ARGS=--explore   # the plain explorer: what the engine sees
    make viz ARGS=--panels    # the measured report, panel by panel

    python -m viz --panels --save deck.pdf

The studio and the explorer open straight away and answer about whatever
position you put in front of them. The panels take a few seconds first: they
are a report on a live engine, so the engine has to be run before there is
anything to report.
"""

import argparse
import sys

from ai.config import TIME_BUDGET


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m viz",
        description="Explore or explain the gomoku engine.")
    parser.add_argument("--explore", action="store_true",
                        help="the plain explorer instead of the studio")
    parser.add_argument("--panels", action="store_true",
                        help="the measured report instead of the studio")
    parser.add_argument("--budget", type=float, default=TIME_BUDGET,
                        help=f"seconds per move to think with "
                             f"(default: {TIME_BUDGET})")
    parser.add_argument("--save", metavar="PATH",
                        help="write the panels to a PDF instead of opening a "
                             "window (implies --panels)")
    args = parser.parse_args(argv)

    if args.explore:
        from .explore import explore

        print("Click an intersection to place a stone, click it again to "
              "remove it.")
        print("T thinks, Enter plays the engine's move, U undoes, Q quits.")
        explore()
        return 0

    if not (args.panels or args.save):
        from .studio import studio

        print("Five chapters over one position, all measured live.")
        print("Click an intersection to build the position; 1-5 or the arrow "
              "keys change chapter; Q quits.")
        studio(args.budget)
        return 0

    from .measure import collect

    print("Running the engine and measuring...", flush=True)
    data = collect(args.budget)

    survey = data["survey"]
    contested = [row for row in survey if not row["solved"]]
    reached = sum(1 for row in contested if row["depth"] >= 10)
    print(f"  deepest search        {max(r['depth'] for r in survey)} plies")
    print(f"  reached 10+           {reached}/{len(contested)} contested positions")
    print(f"  biggest contributor   {data['ablations']['cases'][0]['name']}")

    from .show import save_pdf, show

    if args.save:
        save_pdf(data, args.save)
        print(f"\nWrote {args.save}")
    else:
        print("\nArrow keys to move through the panels, Q to quit.")
        show(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
