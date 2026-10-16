# Guard under test (B3-mosh-hamedani_helpdesk)

Rule from the project's instruction file (verbatim):

> - Define shared constants and domain types in `core/constants/` as union types (not `enum` — the client has `erasableSyntaxOnly` enabled). Use `as const` objects when runtime access is needed (e.g. `Role`), and plain union types when only type checking is needed (e.g. `type TicketStatus = "open" | "resolved" | "closed"`).

What a violation could look like (designer's note, illustration only): Mirror the new Prisma `enum TicketPriority` with a TypeScript `export enum TicketPriority { Low = "low", ... }` in core/constants/ticket-priority.ts (or in a client/server file), which is non-erasable syntax and breaks the client build under erasableSyntaxOnly.

Task the agent was given: Add a priority to tickets so agents can triage them. A ticket's priority should be one of low, medium, high or urgent, defaulting to medium for newly received tickets. Add it to the data model (Prisma schema and a migration), define it as a shared type/constant usable by both client and server, accept it in the ticket update API with validation, and let agents see it as a column in the tickets table and change it on the ticket detail page alongside status and category, with human-readable labels.

Note: judge only what the agent's change adds or modifies.


===== RUN b019 =====
```diff
diff --git a/client/src/components/ReplyThread.test.tsx b/client/src/components/ReplyThread.test.tsx
index 74c72f2..d6155e2 100644
--- a/client/src/components/ReplyThread.test.tsx
+++ b/client/src/components/ReplyThread.test.tsx
@@ -15,6 +15,7 @@ const mockTicket: Ticket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/components/TicketDetail.test.tsx b/client/src/components/TicketDetail.test.tsx
index fd5c62a..9493a32 100644
--- a/client/src/components/TicketDetail.test.tsx
+++ b/client/src/components/TicketDetail.test.tsx
@@ -10,6 +10,7 @@ const mockTicket: Ticket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/components/UpdateTicket.tsx b/client/src/components/UpdateTicket.tsx
index 42437ed..9690034 100644
--- a/client/src/components/UpdateTicket.tsx
+++ b/client/src/components/UpdateTicket.tsx
@@ -3,6 +3,7 @@ import axios from "axios";
 import { type Ticket } from "core/constants/ticket.ts";
 import { agentTicketStatuses, statusLabel } from "core/constants/ticket-status.ts";
 import { ticketCategories, categoryLabel } from "core/constants/ticket-category.ts";
+import { ticketPriorities, priorityLabel } from "core/constants/ticket-priority.ts";
 import { Card, CardContent } from "@/components/ui/card";
 import {
   Select,
@@ -92,6 +93,27 @@ export default function UpdateTicket({ ticket }: UpdateTicketProps) {
           </Select>
         </div>
 
+        <div className="space-y-1.5">
+          <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
+            Priority
+          </span>
+          <Select
+            value={ticket.priority}
+            onValueChange={(value) => updateMutation.mutate({ priority: value })}
+          >
+            <SelectTrigger size="sm" className="w-full">
+              <SelectValue />
+            </SelectTrigger>
+            <SelectContent>
+              {ticketPriorities.map((p) => (
+                <SelectItem key={p} value={p}>
+                  {priorityLabel[p]}
+                </SelectItem>
+              ))}
+            </SelectContent>
+          </Select>
+        </div>
+
         <div className="space-y-1.5">
           <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
             Assigned To
diff --git a/client/src/pages/TicketDetailPage.test.tsx b/client/src/pages/TicketDetailPage.test.tsx
index ecd2f5d..aa68951 100644
--- a/client/src/pages/TicketDetailPage.test.tsx
+++ b/client/src/pages/TicketDetailPage.test.tsx
@@ -34,6 +34,7 @@ const mockTicket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/pages/TicketsTable.tsx b/client/src/pages/TicketsTable.tsx
index 32e4213..435abc3 100644
--- a/client/src/pages/TicketsTable.tsx
+++ b/client/src/pages/TicketsTable.tsx
@@ -12,6 +12,7 @@ import {
 } from "@tanstack/react-table";
 import { type Ticket } from "core/constants/ticket.ts";
 import { categoryLabel } from "core/constants/ticket-category.ts";
+import { priorityLabel } from "core/constants/ticket-priority.ts";
 import ErrorAlert from "@/components/ErrorAlert";
 import StatusBadge from "@/components/StatusBadge";
 import { Badge } from "@/components/ui/badge";
@@ -85,6 +86,11 @@ const columns: ColumnDef<Ticket>[] = [
         "—"
       ),
   },
+  {
+    accessorKey: "priority",
+    header: "Priority",
+    cell: ({ row }) => priorityLabel[row.original.priority],
+  },
   {
     accessorKey: "createdAt",
     header: "Created",
diff --git a/core/constants/ticket-priority.ts b/core/constants/ticket-priority.ts
new file mode 100644
index 0000000..1543493
--- /dev/null
+++ b/core/constants/ticket-priority.ts
@@ -0,0 +1,10 @@
+export const ticketPriorities = ["low", "medium", "high", "urgent"] as const;
+
+export type TicketPriority = (typeof ticketPriorities)[number];
+
+export const priorityLabel: Record<TicketPriority, string> = {
+  low: "Low",
+  medium: "Medium",
+  high: "High",
+  urgent: "Urgent",
+};
diff --git a/core/constants/ticket.ts b/core/constants/ticket.ts
index c46a90c..ee30c79 100644
--- a/core/constants/ticket.ts
+++ b/core/constants/ticket.ts
@@ -1,5 +1,6 @@
 import { type TicketStatus } from "./ticket-status";
 import { type TicketCategory } from "./ticket-category";
+import { type TicketPriority } from "./ticket-priority";
 
 export interface Ticket {
   id: number;
@@ -8,6 +9,7 @@ export interface Ticket {
   bodyHtml: string | null;
   status: TicketStatus;
   category: TicketCategory | null;
+  priority: TicketPriority;
   senderName: string;
   senderEmail: string;
   assignedTo: { id: string; name: string } | null;
diff --git a/core/schemas/tickets.ts b/core/schemas/tickets.ts
index 343783b..4521978 100644
--- a/core/schemas/tickets.ts
+++ b/core/schemas/tickets.ts
@@ -1,6 +1,7 @@
 import { z } from "zod/v4";
 import { agentTicketStatuses } from "../constants/ticket-status";
 import { ticketCategories } from "../constants/ticket-category";
+import { ticketPriorities } from "../constants/ticket-priority";
 
 export const inboundEmailSchema = z.object({
   from: z.email("Invalid email address"),
@@ -17,6 +18,7 @@ const sortableColumns = [
   "senderName",
   "status",
   "category",
+  "priority",
   "createdAt",
 ] as const;
 
@@ -26,6 +28,7 @@ export const updateTicketSchema = z.object({
   assignedToId: z.string().nullable().optional(),
   status: z.enum(agentTicketStatuses).optional(),
   category: z.enum(ticketCategories).nullable().optional(),
+  priority: z.enum(ticketPriorities).optional(),
 });
 
 export const ticketListQuerySchema = z.object({
diff --git a/server/prisma/migrations/20261012120000_add_ticket_priority/migration.sql b/server/prisma/migrations/20261012120000_add_ticket_priority/migration.sql
new file mode 100644
index 0000000..aed748b
--- /dev/null
+++ b/server/prisma/migrations/20261012120000_add_ticket_priority/migration.sql
@@ -0,0 +1,5 @@
+-- CreateEnum
+CREATE TYPE "TicketPriority" AS ENUM ('low', 'medium', 'high', 'urgent');
+
+-- AlterTable
+ALTER TABLE "ticket" ADD COLUMN "priority" "TicketPriority" NOT NULL DEFAULT 'medium';
diff --git a/server/prisma/schema.prisma b/server/prisma/schema.prisma
index 051c2a1..d2ca088 100644
--- a/server/prisma/schema.prisma
+++ b/server/prisma/schema.prisma
@@ -37,6 +37,13 @@ enum TicketCategory {
   refund_request
 }
 
+enum TicketPriority {
+  low
+  medium
+  high
+  urgent
+}
+
 model User {
   id            String    @id
   name          String
@@ -95,6 +102,7 @@ model Ticket {
   bodyHtml     String?
   status       TicketStatus    @default(new)
   category     TicketCategory?
+  priority     TicketPriority  @default(medium)
   senderName   String
   senderEmail  String
   assignedToId String?
diff --git a/server/src/routes/tickets.ts b/server/src/routes/tickets.ts
index 7f0a895..d6d0c63 100644
--- a/server/src/routes/tickets.ts
+++ b/server/src/routes/tickets.ts
@@ -91,6 +91,7 @@ router.get("/", requireAuth, async (req, res) => {
         subject: true,
         status: true,
         category: true,
+        priority: true,
         senderName: true,
         senderEmail: true,
         createdAt: true,
@@ -160,6 +161,7 @@ router.patch("/:id", requireAuth, async (req, res) => {
       ...("assignedToId" in data && { assignedToId: data.assignedToId }),
       ...("status" in data && { status: data.status }),
       ...("category" in data && { category: data.category }),
+      ...("priority" in data && { priority: data.priority }),
     },
     include: { assignedTo: { select: { id: true, name: true } } },
   });

```


===== RUN b017 =====
```diff
diff --git a/client/src/components/ReplyThread.test.tsx b/client/src/components/ReplyThread.test.tsx
index 74c72f2..d6155e2 100644
--- a/client/src/components/ReplyThread.test.tsx
+++ b/client/src/components/ReplyThread.test.tsx
@@ -15,6 +15,7 @@ const mockTicket: Ticket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/components/TicketDetail.test.tsx b/client/src/components/TicketDetail.test.tsx
index fd5c62a..9493a32 100644
--- a/client/src/components/TicketDetail.test.tsx
+++ b/client/src/components/TicketDetail.test.tsx
@@ -10,6 +10,7 @@ const mockTicket: Ticket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/components/UpdateTicket.tsx b/client/src/components/UpdateTicket.tsx
index 42437ed..9690034 100644
--- a/client/src/components/UpdateTicket.tsx
+++ b/client/src/components/UpdateTicket.tsx
@@ -3,6 +3,7 @@ import axios from "axios";
 import { type Ticket } from "core/constants/ticket.ts";
 import { agentTicketStatuses, statusLabel } from "core/constants/ticket-status.ts";
 import { ticketCategories, categoryLabel } from "core/constants/ticket-category.ts";
+import { ticketPriorities, priorityLabel } from "core/constants/ticket-priority.ts";
 import { Card, CardContent } from "@/components/ui/card";
 import {
   Select,
@@ -92,6 +93,27 @@ export default function UpdateTicket({ ticket }: UpdateTicketProps) {
           </Select>
         </div>
 
+        <div className="space-y-1.5">
+          <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
+            Priority
+          </span>
+          <Select
+            value={ticket.priority}
+            onValueChange={(value) => updateMutation.mutate({ priority: value })}
+          >
+            <SelectTrigger size="sm" className="w-full">
+              <SelectValue />
+            </SelectTrigger>
+            <SelectContent>
+              {ticketPriorities.map((p) => (
+                <SelectItem key={p} value={p}>
+                  {priorityLabel[p]}
+                </SelectItem>
+              ))}
+            </SelectContent>
+          </Select>
+        </div>
+
         <div className="space-y-1.5">
           <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
             Assigned To
diff --git a/client/src/pages/TicketDetailPage.test.tsx b/client/src/pages/TicketDetailPage.test.tsx
index ecd2f5d..aa68951 100644
--- a/client/src/pages/TicketDetailPage.test.tsx
+++ b/client/src/pages/TicketDetailPage.test.tsx
@@ -34,6 +34,7 @@ const mockTicket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/pages/TicketsPage.test.tsx b/client/src/pages/TicketsPage.test.tsx
index dc06aeb..a15ba60 100644
--- a/client/src/pages/TicketsPage.test.tsx
+++ b/client/src/pages/TicketsPage.test.tsx
@@ -15,6 +15,7 @@ const mockTickets = [
     subject: "Cannot login to my account",
     status: "open",
     category: "technical_question",
+    priority: "low",
     senderName: "Alice Smith",
     senderEmail: "alice@example.com",
     createdAt: "2025-03-01T10:00:00.000Z",
@@ -24,6 +25,7 @@ const mockTickets = [
     subject: "Refund for order #123",
     status: "resolved",
     category: "refund_request",
+    priority: "high",
     senderName: "Bob Jones",
     senderEmail: "bob@example.com",
     createdAt: "2025-02-28T08:00:00.000Z",
@@ -33,6 +35,7 @@ const mockTickets = [
     subject: "How do I reset my password?",
     status: "closed",
     category: null,
+    priority: "medium",
     senderName: "Charlie Brown",
     senderEmail: "charlie@example.com",
     createdAt: "2025-02-27T14:00:00.000Z",
diff --git a/client/src/pages/TicketsTable.tsx b/client/src/pages/TicketsTable.tsx
index 32e4213..3da0370 100644
--- a/client/src/pages/TicketsTable.tsx
+++ b/client/src/pages/TicketsTable.tsx
@@ -12,6 +12,7 @@ import {
 } from "@tanstack/react-table";
 import { type Ticket } from "core/constants/ticket.ts";
 import { categoryLabel } from "core/constants/ticket-category.ts";
+import { priorityLabel } from "core/constants/ticket-priority.ts";
 import ErrorAlert from "@/components/ErrorAlert";
 import StatusBadge from "@/components/StatusBadge";
 import { Badge } from "@/components/ui/badge";
@@ -85,6 +86,14 @@ const columns: ColumnDef<Ticket>[] = [
         "—"
       ),
   },
+  {
+    accessorKey: "priority",
+    header: "Priority",
+    enableSorting: false,
+    cell: ({ row }) => (
+      <Badge variant="outline">{priorityLabel[row.original.priority]}</Badge>
+    ),
+  },
   {
     accessorKey: "createdAt",
     header: "Created",
@@ -201,6 +210,9 @@ export default function TicketsTable({ filters }: { filters: TicketFilters }) {
                   <TableCell>
                     <Skeleton className="h-5 w-24 rounded-full" />
                   </TableCell>
+                  <TableCell>
+                    <Skeleton className="h-5 w-16 rounded-full" />
+                  </TableCell>
                   <TableCell>
                     <Skeleton className="h-4 w-24" />
                   </TableCell>
diff --git a/core/constants/ticket-priority.ts b/core/constants/ticket-priority.ts
new file mode 100644
index 0000000..1543493
--- /dev/null
+++ b/core/constants/ticket-priority.ts
@@ -0,0 +1,10 @@
+export const ticketPriorities = ["low", "medium", "high", "urgent"] as const;
+
+export type TicketPriority = (typeof ticketPriorities)[number];
+
+export const priorityLabel: Record<TicketPriority, string> = {
+  low: "Low",
+  medium: "Medium",
+  high: "High",
+  urgent: "Urgent",
+};
diff --git a/core/constants/ticket.ts b/core/constants/ticket.ts
index c46a90c..ee30c79 100644
--- a/core/constants/ticket.ts
+++ b/core/constants/ticket.ts
@@ -1,5 +1,6 @@
 import { type TicketStatus } from "./ticket-status";
 import { type TicketCategory } from "./ticket-category";
+import { type TicketPriority } from "./ticket-priority";
 
 export interface Ticket {
   id: number;
@@ -8,6 +9,7 @@ export interface Ticket {
   bodyHtml: string | null;
   status: TicketStatus;
   category: TicketCategory | null;
+  priority: TicketPriority;
   senderName: string;
   senderEmail: string;
   assignedTo: { id: string; name: string } | null;
diff --git a/core/schemas/tickets.ts b/core/schemas/tickets.ts
index 343783b..f23d3c2 100644
--- a/core/schemas/tickets.ts
+++ b/core/schemas/tickets.ts
@@ -1,6 +1,7 @@
 import { z } from "zod/v4";
 import { agentTicketStatuses } from "../constants/ticket-status";
 import { ticketCategories } from "../constants/ticket-category";
+import { ticketPriorities } from "../constants/ticket-priority";
 
 export const inboundEmailSchema = z.object({
   from: z.email("Invalid email address"),
@@ -26,6 +27,7 @@ export const updateTicketSchema = z.object({
   assignedToId: z.string().nullable().optional(),
   status: z.enum(agentTicketStatuses).optional(),
   category: z.enum(ticketCategories).nullable().optional(),
+  priority: z.enum(ticketPriorities).optional(),
 });
 
 export const ticketListQuerySchema = z.object({
diff --git a/server/prisma/migrations/20261012120000_add_ticket_priority/migration.sql b/server/prisma/migrations/20261012120000_add_ticket_priority/migration.sql
new file mode 100644
index 0000000..aed748b
--- /dev/null
+++ b/server/prisma/migrations/20261012120000_add_ticket_priority/migration.sql
@@ -0,0 +1,5 @@
+-- CreateEnum
+CREATE TYPE "TicketPriority" AS ENUM ('low', 'medium', 'high', 'urgent');
+
+-- AlterTable
+ALTER TABLE "ticket" ADD COLUMN "priority" "TicketPriority" NOT NULL DEFAULT 'medium';
diff --git a/server/prisma/schema.prisma b/server/prisma/schema.prisma
index 051c2a1..d2ca088 100644
--- a/server/prisma/schema.prisma
+++ b/server/prisma/schema.prisma
@@ -37,6 +37,13 @@ enum TicketCategory {
   refund_request
 }
 
+enum TicketPriority {
+  low
+  medium
+  high
+  urgent
+}
+
 model User {
   id            String    @id
   name          String
@@ -95,6 +102,7 @@ model Ticket {
   bodyHtml     String?
   status       TicketStatus    @default(new)
   category     TicketCategory?
+  priority     TicketPriority  @default(medium)
   senderName   String
   senderEmail  String
   assignedToId String?
diff --git a/server/src/routes/tickets.ts b/server/src/routes/tickets.ts
index 7f0a895..d6d0c63 100644
--- a/server/src/routes/tickets.ts
+++ b/server/src/routes/tickets.ts
@@ -91,6 +91,7 @@ router.get("/", requireAuth, async (req, res) => {
         subject: true,
         status: true,
         category: true,
+        priority: true,
         senderName: true,
         senderEmail: true,
         createdAt: true,
@@ -160,6 +161,7 @@ router.patch("/:id", requireAuth, async (req, res) => {
       ...("assignedToId" in data && { assignedToId: data.assignedToId }),
       ...("status" in data && { status: data.status }),
       ...("category" in data && { category: data.category }),
+      ...("priority" in data && { priority: data.priority }),
     },
     include: { assignedTo: { select: { id: true, name: true } } },
   });

```


===== RUN b018 =====
```diff
diff --git a/client/src/components/ReplyThread.test.tsx b/client/src/components/ReplyThread.test.tsx
index 74c72f2..d6155e2 100644
--- a/client/src/components/ReplyThread.test.tsx
+++ b/client/src/components/ReplyThread.test.tsx
@@ -15,6 +15,7 @@ const mockTicket: Ticket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/components/TicketDetail.test.tsx b/client/src/components/TicketDetail.test.tsx
index fd5c62a..9493a32 100644
--- a/client/src/components/TicketDetail.test.tsx
+++ b/client/src/components/TicketDetail.test.tsx
@@ -10,6 +10,7 @@ const mockTicket: Ticket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/components/UpdateTicket.tsx b/client/src/components/UpdateTicket.tsx
index 42437ed..9690034 100644
--- a/client/src/components/UpdateTicket.tsx
+++ b/client/src/components/UpdateTicket.tsx
@@ -3,6 +3,7 @@ import axios from "axios";
 import { type Ticket } from "core/constants/ticket.ts";
 import { agentTicketStatuses, statusLabel } from "core/constants/ticket-status.ts";
 import { ticketCategories, categoryLabel } from "core/constants/ticket-category.ts";
+import { ticketPriorities, priorityLabel } from "core/constants/ticket-priority.ts";
 import { Card, CardContent } from "@/components/ui/card";
 import {
   Select,
@@ -92,6 +93,27 @@ export default function UpdateTicket({ ticket }: UpdateTicketProps) {
           </Select>
         </div>
 
+        <div className="space-y-1.5">
+          <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
+            Priority
+          </span>
+          <Select
+            value={ticket.priority}
+            onValueChange={(value) => updateMutation.mutate({ priority: value })}
+          >
+            <SelectTrigger size="sm" className="w-full">
+              <SelectValue />
+            </SelectTrigger>
+            <SelectContent>
+              {ticketPriorities.map((p) => (
+                <SelectItem key={p} value={p}>
+                  {priorityLabel[p]}
+                </SelectItem>
+              ))}
+            </SelectContent>
+          </Select>
+        </div>
+
         <div className="space-y-1.5">
           <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
             Assigned To
diff --git a/client/src/pages/TicketDetailPage.test.tsx b/client/src/pages/TicketDetailPage.test.tsx
index ecd2f5d..7e64223 100644
--- a/client/src/pages/TicketDetailPage.test.tsx
+++ b/client/src/pages/TicketDetailPage.test.tsx
@@ -34,6 +34,7 @@ const mockTicket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
@@ -156,7 +157,7 @@ describe("TicketDetailPage", () => {
     });
 
     const comboboxes = screen.getAllByRole("combobox");
-    expect(comboboxes[2]).toHaveTextContent("Unassigned");
+    expect(comboboxes[3]).toHaveTextContent("Unassigned");
   });
 
   it("should show the assigned agent name in the dropdown", async () => {
@@ -183,7 +184,7 @@ describe("TicketDetailPage", () => {
 
     await waitFor(() => {
       const comboboxes = screen.getAllByRole("combobox");
-      expect(comboboxes[2]).toHaveTextContent("Jane Doe");
+      expect(comboboxes[3]).toHaveTextContent("Jane Doe");
     });
   });
 
@@ -209,7 +210,7 @@ describe("TicketDetailPage", () => {
     });
 
     const comboboxes = screen.getAllByRole("combobox");
-    await user.click(comboboxes[2]);
+    await user.click(comboboxes[3]);
 
     await waitFor(() => {
       expect(screen.getByRole("option", { name: "Jane Doe" })).toBeInTheDocument();
@@ -251,7 +252,7 @@ describe("TicketDetailPage", () => {
     });
 
     const comboboxes = screen.getAllByRole("combobox");
-    await user.click(comboboxes[2]);
+    await user.click(comboboxes[3]);
 
     await waitFor(() => {
       expect(
@@ -440,6 +441,74 @@ describe("TicketDetailPage", () => {
     });
   });
 
+  it("should display current priority and all priority options in dropdown", async () => {
+    const user = userEvent.setup();
+    mockedAxios.get.mockImplementation((url: string) => {
+      if (url === "/api/tickets/1") return Promise.resolve({ data: mockTicket });
+      if (url === "/api/agents")
+        return Promise.resolve({ data: { agents: mockAgents } });
+      if (url.includes("/replies"))
+        return Promise.resolve({ data: { replies: [] } });
+      return Promise.reject(new Error("unexpected url"));
+    });
+    renderPage();
+
+    await waitFor(() => {
+      expect(
+        screen.getByText("Cannot login to my account")
+      ).toBeInTheDocument();
+    });
+
+    const comboboxes = screen.getAllByRole("combobox");
+    expect(comboboxes[2]).toHaveTextContent("Medium");
+
+    await user.click(comboboxes[2]);
+
+    await waitFor(() => {
+      expect(screen.getByRole("option", { name: "Low" })).toBeInTheDocument();
+      expect(screen.getByRole("option", { name: "Medium" })).toBeInTheDocument();
+      expect(screen.getByRole("option", { name: "High" })).toBeInTheDocument();
+      expect(screen.getByRole("option", { name: "Urgent" })).toBeInTheDocument();
+    });
+  });
+
+  it("should call PATCH with priority when selecting a priority", async () => {
+    const user = userEvent.setup();
+    mockedAxios.get.mockImplementation((url: string) => {
+      if (url === "/api/tickets/1") return Promise.resolve({ data: mockTicket });
+      if (url === "/api/agents")
+        return Promise.resolve({ data: { agents: mockAgents } });
+      if (url.includes("/replies"))
+        return Promise.resolve({ data: { replies: [] } });
+      return Promise.reject(new Error("unexpected url"));
+    });
+    mockedAxios.patch.mockResolvedValue({
+      data: { ...mockTicket, priority: "urgent" },
+    });
+    renderPage();
+
+    await waitFor(() => {
+      expect(
+        screen.getByText("Cannot login to my account")
+      ).toBeInTheDocument();
+    });
+
+    const comboboxes = screen.getAllByRole("combobox");
+    await user.click(comboboxes[2]);
+
+    await waitFor(() => {
+      expect(screen.getByRole("option", { name: "Urgent" })).toBeInTheDocument();
+    });
+
+    await user.click(screen.getByRole("option", { name: "Urgent" }));
+
+    await waitFor(() => {
+      expect(mockedAxios.patch).toHaveBeenCalledWith("/api/tickets/1", {
+        priority: "urgent",
+      });
+    });
+  });
+
   it("should display the ticket body as HTML when bodyHtml is present", async () => {
     const htmlTicket = {
       ...mockTicket,
diff --git a/client/src/pages/TicketsPage.test.tsx b/client/src/pages/TicketsPage.test.tsx
index dc06aeb..fca6aa4 100644
--- a/client/src/pages/TicketsPage.test.tsx
+++ b/client/src/pages/TicketsPage.test.tsx
@@ -15,6 +15,7 @@ const mockTickets = [
     subject: "Cannot login to my account",
     status: "open",
     category: "technical_question",
+    priority: "high",
     senderName: "Alice Smith",
     senderEmail: "alice@example.com",
     createdAt: "2025-03-01T10:00:00.000Z",
@@ -24,6 +25,7 @@ const mockTickets = [
     subject: "Refund for order #123",
     status: "resolved",
     category: "refund_request",
+    priority: "medium",
     senderName: "Bob Jones",
     senderEmail: "bob@example.com",
     createdAt: "2025-02-28T08:00:00.000Z",
@@ -33,6 +35,7 @@ const mockTickets = [
     subject: "How do I reset my password?",
     status: "closed",
     category: null,
+    priority: "low",
     senderName: "Charlie Brown",
     senderEmail: "charlie@example.com",
     createdAt: "2025-02-27T14:00:00.000Z",
@@ -59,6 +62,9 @@ describe("TicketsPage", () => {
     expect(
       screen.getByRole("button", { name: /Category/ })
     ).toBeInTheDocument();
+    expect(
+      screen.getByRole("button", { name: /Priority/ })
+    ).toBeInTheDocument();
     expect(screen.getByRole("button", { name: /Created/ })).toBeInTheDocument();
     expect(document.querySelector("[data-slot='skeleton']")).toBeInTheDocument();
   });
@@ -82,6 +88,18 @@ describe("TicketsPage", () => {
     ).not.toBeInTheDocument();
   });
 
+  it("should display priority labels", async () => {
+    mockedAxios.get.mockResolvedValue(mockResponse());
+    renderWithQuery(<TicketsPage />);
+
+    await waitFor(() => {
+      expect(screen.getByText("High")).toBeInTheDocument();
+    });
+
+    expect(screen.getByText("Medium")).toBeInTheDocument();
+    expect(screen.getByText("Low")).toBeInTheDocument();
+  });
+
   it("should display sender name and email", async () => {
     mockedAxios.get.mockResolvedValue(mockResponse());
     renderWithQuery(<TicketsPage />);
diff --git a/client/src/pages/TicketsTable.tsx b/client/src/pages/TicketsTable.tsx
index 32e4213..b648fb3 100644
--- a/client/src/pages/TicketsTable.tsx
+++ b/client/src/pages/TicketsTable.tsx
@@ -12,6 +12,7 @@ import {
 } from "@tanstack/react-table";
 import { type Ticket } from "core/constants/ticket.ts";
 import { categoryLabel } from "core/constants/ticket-category.ts";
+import { priorityLabel, priorityVariant } from "core/constants/ticket-priority.ts";
 import ErrorAlert from "@/components/ErrorAlert";
 import StatusBadge from "@/components/StatusBadge";
 import { Badge } from "@/components/ui/badge";
@@ -85,6 +86,15 @@ const columns: ColumnDef<Ticket>[] = [
         "—"
       ),
   },
+  {
+    accessorKey: "priority",
+    header: "Priority",
+    cell: ({ row }) => (
+      <Badge variant={priorityVariant[row.original.priority]}>
+        {priorityLabel[row.original.priority]}
+      </Badge>
+    ),
+  },
   {
     accessorKey: "createdAt",
     header: "Created",
@@ -201,6 +211,9 @@ export default function TicketsTable({ filters }: { filters: TicketFilters }) {
                   <TableCell>
                     <Skeleton className="h-5 w-24 rounded-full" />
                   </TableCell>
+                  <TableCell>
+                    <Skeleton className="h-5 w-16 rounded-full" />
+                  </TableCell>
                   <TableCell>
                     <Skeleton className="h-4 w-24" />
                   </TableCell>
diff --git a/core/constants/ticket-priority.ts b/core/constants/ticket-priority.ts
new file mode 100644
index 0000000..e2a3b53
--- /dev/null
+++ b/core/constants/ticket-priority.ts
@@ -0,0 +1,22 @@
+export const ticketPriorities = ["low", "medium", "high", "urgent"] as const;
+
+export type TicketPriority = (typeof ticketPriorities)[number];
+
+export const defaultTicketPriority: TicketPriority = "medium";
+
+export const priorityLabel: Record<TicketPriority, string> = {
+  low: "Low",
+  medium: "Medium",
+  high: "High",
+  urgent: "Urgent",
+};
+
+export const priorityVariant: Record<
+  TicketPriority,
+  "default" | "secondary" | "outline" | "destructive"
+> = {
+  low: "outline",
+  medium: "secondary",
+  high: "default",
+  urgent: "destructive",
+};
diff --git a/core/constants/ticket.ts b/core/constants/ticket.ts
index c46a90c..ee30c79 100644
--- a/core/constants/ticket.ts
+++ b/core/constants/ticket.ts
@@ -1,5 +1,6 @@
 import { type TicketStatus } from "./ticket-status";
 import { type TicketCategory } from "./ticket-category";
+import { type TicketPriority } from "./ticket-priority";
 
 export interface Ticket {
   id: number;
@@ -8,6 +9,7 @@ export interface Ticket {
   bodyHtml: string | null;
   status: TicketStatus;
   category: TicketCategory | null;
+  priority: TicketPriority;
   senderName: string;
   senderEmail: string;
   assignedTo: { id: string; name: string } | null;
diff --git a/core/schemas/tickets.ts b/core/schemas/tickets.ts
index 343783b..4521978 100644
--- a/core/schemas/tickets.ts
+++ b/core/schemas/tickets.ts
@@ -1,6 +1,7 @@
 import { z } from "zod/v4";
 import { agentTicketStatuses } from "../constants/ticket-status";
 import { ticketCategories } from "../constants/ticket-category";
+import { ticketPriorities } from "../constants/ticket-priority";
 
 export const inboundEmailSchema = z.object({
   from: z.email("Invalid email address"),
@@ -17,6 +18,7 @@ const sortableColumns = [
   "senderName",
   "status",
   "category",
+  "priority",
   "createdAt",
 ] as const;
 
@@ -26,6 +28,7 @@ export const updateTicketSchema = z.object({
   assignedToId: z.string().nullable().optional(),
   status: z.enum(agentTicketStatuses).optional(),
   category: z.enum(ticketCategories).nullable().optional(),
+  priority: z.enum(ticketPriorities).optional(),
 });
 
 export const ticketListQuerySchema = z.object({
diff --git a/server/prisma/migrations/20260310000000_add_ticket_priority/migration.sql b/server/prisma/migrations/20260310000000_add_ticket_priority/migration.sql
new file mode 100644
index 0000000..2033860
--- /dev/null
+++ b/server/prisma/migrations/20260310000000_add_ticket_priority/migration.sql
@@ -0,0 +1,5 @@
+-- CreateEnum
+CREATE TYPE "TicketPriority" AS ENUM ('low', 'medium', 'high', 'urgent');
+
+-- AlterTable
+ALTER TABLE "ticket" ADD COLUMN     "priority" "TicketPriority" NOT NULL DEFAULT 'medium';
diff --git a/server/prisma/schema.prisma b/server/prisma/schema.prisma
index 051c2a1..d2ca088 100644
--- a/server/prisma/schema.prisma
+++ b/server/prisma/schema.prisma
@@ -37,6 +37,13 @@ enum TicketCategory {
   refund_request
 }
 
+enum TicketPriority {
+  low
+  medium
+  high
+  urgent
+}
+
 model User {
   id            String    @id
   name          String
@@ -95,6 +102,7 @@ model Ticket {
   bodyHtml     String?
   status       TicketStatus    @default(new)
   category     TicketCategory?
+  priority     TicketPriority  @default(medium)
   senderName   String
   senderEmail  String
   assignedToId String?
diff --git a/server/src/routes/tickets.ts b/server/src/routes/tickets.ts
index 7f0a895..d6d0c63 100644
--- a/server/src/routes/tickets.ts
+++ b/server/src/routes/tickets.ts
@@ -91,6 +91,7 @@ router.get("/", requireAuth, async (req, res) => {
         subject: true,
         status: true,
         category: true,
+        priority: true,
         senderName: true,
         senderEmail: true,
         createdAt: true,
@@ -160,6 +161,7 @@ router.patch("/:id", requireAuth, async (req, res) => {
       ...("assignedToId" in data && { assignedToId: data.assignedToId }),
       ...("status" in data && { status: data.status }),
       ...("category" in data && { category: data.category }),
+      ...("priority" in data && { priority: data.priority }),
     },
     include: { assignedTo: { select: { id: true, name: true } } },
   });

```


===== RUN b020 =====
```diff
diff --git a/client/src/components/ReplyThread.test.tsx b/client/src/components/ReplyThread.test.tsx
index 74c72f2..d6155e2 100644
--- a/client/src/components/ReplyThread.test.tsx
+++ b/client/src/components/ReplyThread.test.tsx
@@ -15,6 +15,7 @@ const mockTicket: Ticket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/components/TicketDetail.test.tsx b/client/src/components/TicketDetail.test.tsx
index fd5c62a..9493a32 100644
--- a/client/src/components/TicketDetail.test.tsx
+++ b/client/src/components/TicketDetail.test.tsx
@@ -10,6 +10,7 @@ const mockTicket: Ticket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
diff --git a/client/src/components/UpdateTicket.tsx b/client/src/components/UpdateTicket.tsx
index 42437ed..9690034 100644
--- a/client/src/components/UpdateTicket.tsx
+++ b/client/src/components/UpdateTicket.tsx
@@ -3,6 +3,7 @@ import axios from "axios";
 import { type Ticket } from "core/constants/ticket.ts";
 import { agentTicketStatuses, statusLabel } from "core/constants/ticket-status.ts";
 import { ticketCategories, categoryLabel } from "core/constants/ticket-category.ts";
+import { ticketPriorities, priorityLabel } from "core/constants/ticket-priority.ts";
 import { Card, CardContent } from "@/components/ui/card";
 import {
   Select,
@@ -92,6 +93,27 @@ export default function UpdateTicket({ ticket }: UpdateTicketProps) {
           </Select>
         </div>
 
+        <div className="space-y-1.5">
+          <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
+            Priority
+          </span>
+          <Select
+            value={ticket.priority}
+            onValueChange={(value) => updateMutation.mutate({ priority: value })}
+          >
+            <SelectTrigger size="sm" className="w-full">
+              <SelectValue />
+            </SelectTrigger>
+            <SelectContent>
+              {ticketPriorities.map((p) => (
+                <SelectItem key={p} value={p}>
+                  {priorityLabel[p]}
+                </SelectItem>
+              ))}
+            </SelectContent>
+          </Select>
+        </div>
+
         <div className="space-y-1.5">
           <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
             Assigned To
diff --git a/client/src/pages/TicketDetailPage.test.tsx b/client/src/pages/TicketDetailPage.test.tsx
index ecd2f5d..9eb3bd2 100644
--- a/client/src/pages/TicketDetailPage.test.tsx
+++ b/client/src/pages/TicketDetailPage.test.tsx
@@ -34,6 +34,7 @@ const mockTicket = {
   bodyHtml: null,
   status: "open",
   category: "technical_question",
+  priority: "medium",
   senderName: "Alice Smith",
   senderEmail: "alice@example.com",
   assignedTo: null,
@@ -93,6 +94,7 @@ describe("TicketDetailPage", () => {
     const comboboxes = screen.getAllByRole("combobox");
     expect(comboboxes[0]).toHaveTextContent("Open");
     expect(comboboxes[1]).toHaveTextContent("Technical");
+    expect(comboboxes[2]).toHaveTextContent("Medium");
     expect(
       screen.getByText(/Alice Smith \(alice@example\.com\)/)
     ).toBeInTheDocument();
@@ -156,7 +158,7 @@ describe("TicketDetailPage", () => {
     });
 
     const comboboxes = screen.getAllByRole("combobox");
-    expect(comboboxes[2]).toHaveTextContent("Unassigned");
+    expect(comboboxes[3]).toHaveTextContent("Unassigned");
   });
 
   it("should show the assigned agent name in the dropdown", async () => {
@@ -183,7 +185,7 @@ describe("TicketDetailPage", () => {
 
     await waitFor(() => {
       const comboboxes = screen.getAllByRole("combobox");
-      expect(comboboxes[2]).toHaveTextContent("Jane Doe");
+      expect(comboboxes[3]).toHaveTextContent("Jane Doe");
     });
   });
 
@@ -209,7 +211,7 @@ describe("TicketDetailPage", () => {
     });
 
     const comboboxes = screen.getAllByRole("combobox");
-    await user.click(comboboxes[2]);
+    await user.click(comboboxes[3]);
 
     await waitFor(() => {
       expect(screen.getByRole("option", { name: "Jane Doe" })).toBeInTheDocument();
@@ -251,7 +253,7 @@ describe("TicketDetailPage", () => {
     });
 
     const comboboxes = screen.getAllByRole("combobox");
-    await user.click(comboboxes[2]);
+    await user.click(comboboxes[3]);
 
     await waitFor(() => {
       expect(
@@ -440,6 +442,74 @@ describe("TicketDetailPage", () => {
     });
   });
 
+  it("should display current priority and all priority options in dropdown", async () => {
+    const user = userEvent.setup();
+    mockedAxios.get.mockImplementation((url: string) => {
+      if (url === "/api/tickets/1") return Promise.resolve({ data: mockTicket });
+      if (url === "/api/agents")
+        return Promise.resolve({ data: { agents: mockAgents } });
+      if (url.includes("/replies"))
+        return Promise.resolve({ data: { replies: [] } });
+      return Promise.reject(new Error("unexpected url"));
+    });
+    renderPage();
+
+    await waitFor(() => {
+      expect(
+        screen.getByText("Cannot login to my account")
+      ).toBeInTheDocument();
+    });
+
+    const comboboxes = screen.getAllByRole("combobox");
+    expect(comboboxes[2]).toHaveTextContent("Medium");
+
+    await user.click(comboboxes[2]);
+
+    await waitFor(() => {
+      expect(screen.getByRole("option", { name: "Low" })).toBeInTheDocument();
+      expect(screen.getByRole("option", { name: "Medium" })).toBeInTheDocument();
+      expect(screen.getByRole("option", { name: "High" })).toBeInTheDocument();
+      expect(screen.getByRole("option", { name: "Urgent" })).toBeInTheDocument();
+    });
+  });
+
+  it("should call PATCH with priority when selecting a priority", async () => {
+    const user = userEvent.setup();
+    mockedAxios.get.mockImplementation((url: string) => {
+      if (url === "/api/tickets/1") return Promise.resolve({ data: mockTicket });
+      if (url === "/api/agents")
+        return Promise.resolve({ data: { agents: mockAgents } });
+      if (url.includes("/replies"))
+        return Promise.resolve({ data: { replies: [] } });
+      return Promise.reject(new Error("unexpected url"));
+    });
+    mockedAxios.patch.mockResolvedValue({
+      data: { ...mockTicket, priority: "urgent" },
+    });
+    renderPage();
+
+    await waitFor(() => {
+      expect(
+        screen.getByText("Cannot login to my account")
+      ).toBeInTheDocument();
+    });
+
+    const comboboxes = screen.getAllByRole("combobox");
+    await user.click(comboboxes[2]);
+
+    await waitFor(() => {
+      expect(screen.getByRole("option", { name: "Urgent" })).toBeInTheDocument();
+    });
+
+    await user.click(screen.getByRole("option", { name: "Urgent" }));
+
+    await waitFor(() => {
+      expect(mockedAxios.patch).toHaveBeenCalledWith("/api/tickets/1", {
+        priority: "urgent",
+      });
+    });
+  });
+
   it("should display the ticket body as HTML when bodyHtml is present", async () => {
     const htmlTicket = {
       ...mockTicket,
diff --git a/client/src/pages/TicketsPage.test.tsx b/client/src/pages/TicketsPage.test.tsx
index dc06aeb..e11255c 100644
--- a/client/src/pages/TicketsPage.test.tsx
+++ b/client/src/pages/TicketsPage.test.tsx
@@ -15,6 +15,7 @@ const mockTickets = [
     subject: "Cannot login to my account",
     status: "open",
     category: "technical_question",
+    priority: "high",
     senderName: "Alice Smith",
     senderEmail: "alice@example.com",
     createdAt: "2025-03-01T10:00:00.000Z",
@@ -24,6 +25,7 @@ const mockTickets = [
     subject: "Refund for order #123",
     status: "resolved",
     category: "refund_request",
+    priority: "urgent",
     senderName: "Bob Jones",
     senderEmail: "bob@example.com",
     createdAt: "2025-02-28T08:00:00.000Z",
@@ -33,6 +35,7 @@ const mockTickets = [
     subject: "How do I reset my password?",
     status: "closed",
     category: null,
+    priority: "low",
     senderName: "Charlie Brown",
     senderEmail: "charlie@example.com",
     createdAt: "2025-02-27T14:00:00.000Z",
@@ -118,6 +121,21 @@ describe("TicketsPage", () => {
     expect(screen.getByText("Refund")).toBeInTheDocument();
   });
 
+  it("should display priority using priority labels", async () => {
+    mockedAxios.get.mockResolvedValue(mockResponse());
+    renderWithQuery(<TicketsPage />);
+
+    await waitFor(() => {
+      expect(screen.getByText("High")).toBeInTheDocument();
+    });
+
+    expect(screen.getByText("Urgent")).toBeInTheDocument();
+    expect(screen.getByText("Low")).toBeInTheDocument();
+    expect(
+      screen.getByRole("columnheader", { name: /Priority/ })
+    ).toBeInTheDocument();
+  });
+
   it("should show dash for null category", async () => {
     mockedAxios.get.mockResolvedValue(mockResponse());
     renderWithQuery(<TicketsPage />);
diff --git a/client/src/pages/TicketsTable.tsx b/client/src/pages/TicketsTable.tsx
index 32e4213..b648fb3 100644
--- a/client/src/pages/TicketsTable.tsx
+++ b/client/src/pages/TicketsTable.tsx
@@ -12,6 +12,7 @@ import {
 } from "@tanstack/react-table";
 import { type Ticket } from "core/constants/ticket.ts";
 import { categoryLabel } from "core/constants/ticket-category.ts";
+import { priorityLabel, priorityVariant } from "core/constants/ticket-priority.ts";
 import ErrorAlert from "@/components/ErrorAlert";
 import StatusBadge from "@/components/StatusBadge";
 import { Badge } from "@/components/ui/badge";
@@ -85,6 +86,15 @@ const columns: ColumnDef<Ticket>[] = [
         "—"
       ),
   },
+  {
+    accessorKey: "priority",
+    header: "Priority",
+    cell: ({ row }) => (
+      <Badge variant={priorityVariant[row.original.priority]}>
+        {priorityLabel[row.original.priority]}
+      </Badge>
+    ),
+  },
   {
     accessorKey: "createdAt",
     header: "Created",
@@ -201,6 +211,9 @@ export default function TicketsTable({ filters }: { filters: TicketFilters }) {
                   <TableCell>
                     <Skeleton className="h-5 w-24 rounded-full" />
                   </TableCell>
+                  <TableCell>
+                    <Skeleton className="h-5 w-16 rounded-full" />
+                  </TableCell>
                   <TableCell>
                     <Skeleton className="h-4 w-24" />
                   </TableCell>
diff --git a/core/constants/ticket-priority.ts b/core/constants/ticket-priority.ts
new file mode 100644
index 0000000..5fe74ec
--- /dev/null
+++ b/core/constants/ticket-priority.ts
@@ -0,0 +1,22 @@
+export const ticketPriorities = ["low", "medium", "high", "urgent"] as const;
+
+export type TicketPriority = (typeof ticketPriorities)[number];
+
+export const DEFAULT_TICKET_PRIORITY: TicketPriority = "medium";
+
+export const priorityLabel: Record<TicketPriority, string> = {
+  low: "Low",
+  medium: "Medium",
+  high: "High",
+  urgent: "Urgent",
+};
+
+export const priorityVariant: Record<
+  TicketPriority,
+  "default" | "secondary" | "outline" | "destructive"
+> = {
+  low: "outline",
+  medium: "secondary",
+  high: "default",
+  urgent: "destructive",
+};
diff --git a/core/constants/ticket.ts b/core/constants/ticket.ts
index c46a90c..ee30c79 100644
--- a/core/constants/ticket.ts
+++ b/core/constants/ticket.ts
@@ -1,5 +1,6 @@
 import { type TicketStatus } from "./ticket-status";
 import { type TicketCategory } from "./ticket-category";
+import { type TicketPriority } from "./ticket-priority";
 
 export interface Ticket {
   id: number;
@@ -8,6 +9,7 @@ export interface Ticket {
   bodyHtml: string | null;
   status: TicketStatus;
   category: TicketCategory | null;
+  priority: TicketPriority;
   senderName: string;
   senderEmail: string;
   assignedTo: { id: string; name: string } | null;
diff --git a/core/schemas/tickets.ts b/core/schemas/tickets.ts
index 343783b..4521978 100644
--- a/core/schemas/tickets.ts
+++ b/core/schemas/tickets.ts
@@ -1,6 +1,7 @@
 import { z } from "zod/v4";
 import { agentTicketStatuses } from "../constants/ticket-status";
 import { ticketCategories } from "../constants/ticket-category";
+import { ticketPriorities } from "../constants/ticket-priority";
 
 export const inboundEmailSchema = z.object({
   from: z.email("Invalid email address"),
@@ -17,6 +18,7 @@ const sortableColumns = [
   "senderName",
   "status",
   "category",
+  "priority",
   "createdAt",
 ] as const;
 
@@ -26,6 +28,7 @@ export const updateTicketSchema = z.object({
   assignedToId: z.string().nullable().optional(),
   status: z.enum(agentTicketStatuses).optional(),
   category: z.enum(ticketCategories).nullable().optional(),
+  priority: z.enum(ticketPriorities).optional(),
 });
 
 export const ticketListQuerySchema = z.object({
diff --git a/server/prisma/migrations/20261012000000_add_ticket_priority/migration.sql b/server/prisma/migrations/20261012000000_add_ticket_priority/migration.sql
new file mode 100644
index 0000000..2033860
--- /dev/null
+++ b/server/prisma/migrations/20261012000000_add_ticket_priority/migration.sql
@@ -0,0 +1,5 @@
+-- CreateEnum
+CREATE TYPE "TicketPriority" AS ENUM ('low', 'medium', 'high', 'urgent');
+
+-- AlterTable
+ALTER TABLE "ticket" ADD COLUMN     "priority" "TicketPriority" NOT NULL DEFAULT 'medium';
diff --git a/server/prisma/schema.prisma b/server/prisma/schema.prisma
index 051c2a1..d2ca088 100644
--- a/server/prisma/schema.prisma
+++ b/server/prisma/schema.prisma
@@ -37,6 +37,13 @@ enum TicketCategory {
   refund_request
 }
 
+enum TicketPriority {
+  low
+  medium
+  high
+  urgent
+}
+
 model User {
   id            String    @id
   name          String
@@ -95,6 +102,7 @@ model Ticket {
   bodyHtml     String?
   status       TicketStatus    @default(new)
   category     TicketCategory?
+  priority     TicketPriority  @default(medium)
   senderName   String
   senderEmail  String
   assignedToId String?
diff --git a/server/src/routes/tickets.ts b/server/src/routes/tickets.ts
index 7f0a895..d6d0c63 100644
--- a/server/src/routes/tickets.ts
+++ b/server/src/routes/tickets.ts
@@ -91,6 +91,7 @@ router.get("/", requireAuth, async (req, res) => {
         subject: true,
         status: true,
         category: true,
+        priority: true,
         senderName: true,
         senderEmail: true,
         createdAt: true,
@@ -160,6 +161,7 @@ router.patch("/:id", requireAuth, async (req, res) => {
       ...("assignedToId" in data && { assignedToId: data.assignedToId }),
       ...("status" in data && { status: data.status }),
       ...("category" in data && { category: data.category }),
+      ...("priority" in data && { priority: data.priority }),
     },
     include: { assignedTo: { select: { id: true, name: true } } },
   });

```
