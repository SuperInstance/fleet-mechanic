primary_plane: 3
reads_from: [1, 2, 3, 4, 5]
writes_to: [1, 2, 3]
floor: 1
ceiling: 5
compilers:
  - name: deepseek-chat
    from: 4
    to: 2
    locks: 7
reasoning: |
  Fleet-mechanic is the autonomous fixer operating at Plane 3 (structured).
  It must understand the entire stack from native code (1) to natural Intent (5)
  to diagnose and repair issues. It reads all planes to analyze problems and writes
  to planes 1-3 to apply fixes: native patches (1), bytecode updates (2), or
  configuration changes (3).

  Floor at 1 means fleet-mechanic can read and potentially modify native Rust code
  for critical fixes, though it prefers higher-level changes when possible. The
  compiler from Domain Language (4) to Bytecode (2) is essential for generating
  repair scripts that holodeck-rust can embed or flux-runtime can execute.
