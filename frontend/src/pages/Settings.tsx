import { Cpu, Database, SlidersHorizontal, UserRound } from "lucide-react";
import { AccountPanel, ModelPanel, PreferencesPanel, SettingsPage, SystemPanel } from "../components/SettingsPanels";

export default function Settings() {
  return (
    <SettingsPage
      title="Settings"
      subtitle="Your account, interface preferences and information about the model."
      tabs={[
        { id: "account", label: "Account", icon: UserRound, render: () => <AccountPanel /> },
        { id: "preferences", label: "Preferences", icon: SlidersHorizontal, render: () => <PreferencesPanel /> },
        { id: "model", label: "About the model", icon: Cpu, aliases: ["about"], render: () => <ModelPanel /> },
        { id: "system", label: "System status", icon: Database, render: () => <SystemPanel /> },
      ]}
    />
  );
}
