import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import Home from "@/app/page";

const mockBoard = {
    board: { id: "1", title: "My Board" },
    columns: [
        { id: "1", title: "Backlog", position: 0, cardIds: [] },
    ],
    cards: {},
};

const mockBoardWithCard = {
    board: { id: "1", title: "My Board" },
    columns: [
        { id: "1", title: "Backlog", position: 0, cardIds: ["9"] },
    ],
    cards: {
        "9": {
            id: "9",
            title: "AI created",
            details: "From chat",
        },
    },
};

describe("Home page", () => {
    it("shows the login screen by default", () => {
        render(<Home />);
        expect(screen.getByText("Welcome back")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    });

    it("allows signing in with demo credentials", async () => {
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: async () => mockBoard,
            text: async () => "",
        } as Response);

        render(<Home />);
        await userEvent.type(screen.getByPlaceholderText("user"), "user");
        await userEvent.type(screen.getByPlaceholderText("password"), "password");
        await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

        expect(await screen.findByText("Kanban Studio")).toBeInTheDocument();
        vi.restoreAllMocks();
    });

    it("applies chat updates to the board", async () => {
        vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
            const url = String(input);
            if (url.includes("/api/board")) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => mockBoard,
                    text: async () => "",
                } as Response;
            }
            if (url.includes("/api/chat")) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => ({
                        response: "Created a card.",
                        actions: [{ type: "create_card" }],
                        board: mockBoardWithCard,
                    }),
                    text: async () => "",
                } as Response;
            }
            return {
                ok: false,
                status: 500,
                text: async () => "Unexpected",
            } as Response;
        });

        render(<Home />);
        await userEvent.type(screen.getByPlaceholderText("user"), "user");
        await userEvent.type(screen.getByPlaceholderText("password"), "password");
        await userEvent.click(screen.getByRole("button", { name: /sign in/i }));

        expect(await screen.findByText("Kanban Studio")).toBeInTheDocument();

        await userEvent.type(screen.getByLabelText("Chat message"), "Add a card");
        await userEvent.click(screen.getByRole("button", { name: /send/i }));

        expect(await screen.findByText("AI created")).toBeInTheDocument();
        vi.restoreAllMocks();
    });

    it("keeps the board mounted while refreshing after adding a card", async () => {
        vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
            const url = String(input);
            return {
                ok: true,
                status: 200,
                json: async () => (url.includes("/api/cards") ? { id: "9" } : mockBoard),
                text: async () => "",
            } as Response;
        });

        render(<Home />);
        await userEvent.type(screen.getByPlaceholderText("user"), "user");
        await userEvent.type(screen.getByPlaceholderText("password"), "password");
        await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
        expect(await screen.findByText("Kanban Studio")).toBeInTheDocument();

        await userEvent.type(screen.getByLabelText("Chat message"), "Draft question");
        await userEvent.click(screen.getByRole("button", { name: /add a card/i }));
        await userEvent.type(screen.getByPlaceholderText(/card title/i), "New card");
        await userEvent.click(screen.getByRole("button", { name: /add card/i }));

        await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(3));
        expect(screen.queryByText("Loading your board")).not.toBeInTheDocument();
        expect(screen.getByLabelText("Chat message")).toHaveValue("Draft question");
        vi.restoreAllMocks();
    });
});
