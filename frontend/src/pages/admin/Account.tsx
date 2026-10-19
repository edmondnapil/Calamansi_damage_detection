import { Cpu, Database, UserRound } from "lucide-react";
import { AccountPanel, ModelPanel, SettingsPage, SystemPanel } from "../../components/SettingsPanels";

export default function AdminAccount() {
  return (
    <SettingsPage
      title="Settings"
      subtitle="Your administrator account, system status and the model in use."
      tabs={[
        { id: "account", label: "Account", icon: UserRound, render: () => <AccountPanel /> },
        { id: "system", label: "System status", icon: Database, render: () => <SystemPanel /> },
        { id: "model", label: "Model", icon: Cpu, aliases: ["about"], render: () => <ModelPanel /> },
      ]}
    />
  );
}
