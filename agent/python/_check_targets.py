from mango_agent.agent import extract_goal_targets
# try common modules
import importlib
for mod in [
    "mango_agent.resolved_work",
    "mango_agent.work_plan",
    "mango_agent.impl_completeness",
    "mango_agent.goals",
]:
    try:
        m = importlib.import_module(mod)
        if hasattr(m, "extract_goal_targets"):
            print("found in", mod)
            GOAL = (
                "Create a Python CLI tool called wordstats.py that analyzes a text file and "
                "prints word-frequency statistics. Requirements:\n"
                "Takes a file path as a command-line argument\n"
                "Counts word frequency (case-insensitive, ignore punctuation)\n"
                "Prints the top 10 most common words with their counts\n"
                "Handles the file-not-found case gracefully with a clear error message\n"
                "Include unit tests covering: normal input, empty file, and file-not-found\n"
                "Use only the Python standard library"
            )
            t = m.extract_goal_targets(GOAL)
            print("files", getattr(t, "files", t))
            print("symbols", getattr(t, "symbols", None))
    except Exception as e:
        print(mod, type(e).__name__, e)
