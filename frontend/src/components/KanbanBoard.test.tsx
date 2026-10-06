import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { vi } from "vitest";
import { KanbanBoard } from "@/components/KanbanBoard";
import { initialData, type BoardData } from "@/lib/kanban";

const getFirstColumn = () => screen.getAllByTestId(/column-/i)[0];

describe("KanbanBoard", () => {
  const renderBoard = (
    handlers: Partial<Parameters<typeof KanbanBoard>[0]> = {}
  ) => {
    const Wrapper = () => {
      const [board, setBoard] = useState<BoardData>(() => initialData);
      return <KanbanBoard board={board} onBoardChange={setBoard} {...handlers} />;
    };

    render(<Wrapper />);
  };

  it("renders five columns", () => {
    renderBoard();
    expect(screen.getAllByTestId(/column-/i)).toHaveLength(5);
  });

  it("renames a column", async () => {
    renderBoard();
    const column = getFirstColumn();
    const input = within(column).getByLabelText("Column title");
    await userEvent.clear(input);
    await userEvent.type(input, "New Name");
    expect(input).toHaveValue("New Name");
  });

  it("saves a column rename only on blur", async () => {
    const onRenameColumn = vi.fn();
    renderBoard({ onRenameColumn });
    const input = within(getFirstColumn()).getByLabelText("Column title");
    await userEvent.clear(input);
    await userEvent.type(input, "Ideas");
    expect(onRenameColumn).not.toHaveBeenCalled();

    await userEvent.tab();
    expect(onRenameColumn).toHaveBeenCalledTimes(1);
    expect(onRenameColumn).toHaveBeenCalledWith("col-backlog", "Ideas");
    expect(within(getFirstColumn()).getByLabelText("Column title")).toHaveValue("Ideas");
  });

  it("reverts an empty column title without saving", async () => {
    const onRenameColumn = vi.fn();
    renderBoard({ onRenameColumn });
    const input = within(getFirstColumn()).getByLabelText("Column title");
    await userEvent.clear(input);
    await userEvent.keyboard("{Enter}");
    expect(onRenameColumn).not.toHaveBeenCalled();
    expect(input).toHaveValue("Backlog");
  });

  it("edits a card", async () => {
    const onEditCard = vi.fn();
    renderBoard({ onEditCard });
    const column = getFirstColumn();
    await userEvent.click(
      within(column).getByRole("button", { name: /edit align roadmap themes/i })
    );
    const titleInput = within(column).getByLabelText("Card title");
    await userEvent.clear(titleInput);
    await userEvent.type(titleInput, "Roadmap v2");
    await userEvent.click(within(column).getByRole("button", { name: "Save" }));

    expect(within(column).getByText("Roadmap v2")).toBeInTheDocument();
    expect(onEditCard).toHaveBeenCalledWith(
      "card-1",
      "Roadmap v2",
      "Draft quarterly themes with impact statements and metrics."
    );
  });

  it("adds and removes a card", async () => {
    renderBoard();
    const column = getFirstColumn();
    const addButton = within(column).getByRole("button", {
      name: /add a card/i,
    });
    await userEvent.click(addButton);

    const titleInput = within(column).getByPlaceholderText(/card title/i);
    await userEvent.type(titleInput, "New card");
    const detailsInput = within(column).getByPlaceholderText(/details/i);
    await userEvent.type(detailsInput, "Notes");

    await userEvent.click(within(column).getByRole("button", { name: /add card/i }));

    expect(within(column).getByText("New card")).toBeInTheDocument();

    const deleteButton = within(column).getByRole("button", {
      name: /delete new card/i,
    });
    await userEvent.click(deleteButton);

    expect(within(column).queryByText("New card")).not.toBeInTheDocument();
  });
});
