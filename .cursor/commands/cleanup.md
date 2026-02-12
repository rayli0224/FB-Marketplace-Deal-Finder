# cleanup

Clean up and refactor the code to make it clean, robust, well-written, and well-abstracted.

## Code Quality Standards

### Clean Code
- **Remove dead code**: Delete unused functions, variables, imports, and files
- **Eliminate duplication**: Extract repeated logic into reusable functions or constants
- **Simplify complex expressions**: Break down nested ternaries, long conditionals, and convoluted logic
- **Consistent formatting**: Follow project style (indentation, spacing, line breaks)
- **Remove commented-out code**: If it's not needed, delete it (version control preserves history)

### Robust Code
- **Handle edge cases**: Consider null/undefined, empty arrays, boundary conditions
- **Validate inputs**: Check parameters and data before processing
- **Error handling**: Provide meaningful error messages and handle failures gracefully
- **Type safety**: Use proper types/interfaces, avoid `any` unless necessary
- **No silent failures**: Log errors appropriately, don't swallow exceptions without reason

### Well-Written Code
- **Clear naming**: Variables, functions, and classes should be self-documenting
- **Single responsibility**: Each function/class should do one thing well
- **Appropriate abstraction level**: Don't mix high-level and low-level concerns
- **Readable flow**: Code should read top-to-bottom like a story
- **Documentation**: Add docstrings/comments where behavior isn't obvious

### Well-Abstracted Code
- **Separation of concerns**: Business logic separate from UI, data access separate from processing
- **DRY principle**: Don't Repeat Yourself — extract common patterns
- **Proper encapsulation**: Hide implementation details, expose clear interfaces
- **Reusable components**: Extract generic logic that can be used elsewhere
- **Dependency injection**: Depend on abstractions, not concrete implementations

### Follow Project Rules
- **Adhere to coding-standards.mdc**: Function naming, structure, documentation patterns
- **Follow language-specific conventions**: TypeScript/React patterns, Python style guides
- **Respect project architecture**: Don't violate established patterns or file organization
- **Match existing code style**: When in doubt, mirror patterns already in the codebase

## Refactoring Process

**IMPORTANT: Do a COMPLETE cleanup in ONE pass. Do not leave work for future cleanup passes.**

1. **Read the entire file**: Understand the full context and all dependencies
2. **Identify ALL issues**: Systematically check for:
   - All duplication (even small patterns)
   - All complex expressions
   - All unclear names
   - All missing error handling
   - All edge cases
   - All unused code
   - All magic numbers/strings
   - All opportunities for abstraction
3. **Fix everything at once**: Make all necessary changes in a single comprehensive refactoring pass
4. **Preserve behavior**: Ensure functionality remains identical after refactoring
5. **Verify completeness**: Before finishing, review the code one more time to ensure nothing was missed

## Comprehensive Cleanup Checklist

**Review ALL of these in a single pass:**

### Dead Code Removal
- [ ] Unused imports
- [ ] Unused functions/methods
- [ ] Unused variables/constants
- [ ] Unused parameters
- [ ] Commented-out code
- [ ] Unused type definitions/interfaces

### Duplication Elimination
- [ ] Repeated logic patterns (extract to helpers)
- [ ] Repeated string/number literals (extract to constants)
- [ ] Repeated className constructions (extract to functions)
- [ ] Repeated conditional patterns
- [ ] Similar functions that could be unified

### Expression Simplification
- [ ] Nested ternaries (break into if/else or extract functions)
- [ ] Long conditional chains (extract to helper functions)
- [ ] Complex boolean expressions (extract to named functions)
- [ ] Repeated calculations (extract to variables)

### Code Organization
- [ ] Functions ordered logically (group related functions)
- [ ] Constants defined at the top
- [ ] Helper functions before main functions
- [ ] Consistent spacing and formatting

### Abstraction Improvements
- [ ] Extract repeated patterns into reusable functions
- [ ] Separate concerns (UI logic vs business logic)
- [ ] Create helper functions for complex operations
- [ ] Extract constants for configuration values

### Type Safety & Robustness
- [ ] Add missing type annotations
- [ ] Handle null/undefined cases
- [ ] Validate inputs
- [ ] Add edge case handling (empty arrays, boundary conditions)
- [ ] Remove `any` types where possible

### Documentation & Naming
- [ ] Clear, descriptive function names
- [ ] Clear, descriptive variable names
- [ ] Remove comments that just restate code
- [ ] Add docstrings where behavior isn't obvious
- [ ] Ensure all functions have return type annotations

**After completing ALL items above, review the code one final time to ensure nothing was missed.**
