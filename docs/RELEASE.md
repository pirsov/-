# Release Checklist

## Rojo Build Command
```sh
rojo build --manifest default.project.json --output build/game.rbxlx
```

## Publish Checklist
1. **Build the Game**: Run the Rojo build command to generate the game package.
2. **Upload to Hosting**: Upload the `build/game.rbxlx` file to your hosting service.
3. **Update Version**: Update the version number in `default.project.json` and `docs/ARCHITECTURE.md`.
4. **Notify Stakeholders**: Inform relevant stakeholders about the release.
5. **Verify Deployment**: Ensure the game is accessible and functioning correctly on the hosting service.
6. **Document Release**: Update the `docs/RELEASE.md` file with the release notes and any important changes.
7. **Clean Up**: Remove any unnecessary files or artifacts from the build directory.

## Post-Release Steps
1. **Monitor Performance**: Monitor the game's performance and address any issues that arise.
2. **Collect Feedback**: Gather feedback from players and stakeholders to identify areas for improvement.
3. **Update Documentation**: Update the game's documentation to reflect any changes or improvements made during the release.
4. **Prepare for Next Release**: Plan for the next release cycle and update the project's roadmap.

By following these steps, you can ensure a smooth and successful release of your game.
