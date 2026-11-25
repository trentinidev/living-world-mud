"use strict";

const places = {
  "market-square": "Praça do mercado", "east-farm": "Fazenda leste",
  "west-farm": "Fazenda oeste", "north-farm": "Fazenda norte",
  "south-farm": "Fazenda sul", "hill-farm": "Fazenda da colina",
  "river-farm": "Fazenda do rio", woodland: "Bosque", kiln: "Forno de carvão",
  mine: "Mina", smeltery: "Fundição", forge: "Forja da Ada",
};
const farms = {"farm-owner": "east-farm", "west-farm-owner": "west-farm"};
const element = (id) => document.getElementById(id);
const label = (location) => places[location] || location;
let pending = false;
let connected = false;

function button(text, command, duration) {
  const control = document.createElement("button");
  control.type = "button";
  control.dataset.command = command;
  control.textContent = text;
  if (duration !== undefined) {
    const time = document.createElement("span");
    time.className = "road-minutes";
    time.textContent = " " + duration + " min";
    control.append(time);
  }
  return control;
}

function log(message, failed = false) {
  const entries = element("log");
  const line = document.createElement("li");
  line.textContent = message;
  line.classList.toggle("error", failed);
  entries.prepend(line);
  entries.scrollTop = 0;
  if (entries.children.length > 12) entries.lastElementChild.remove();
  const feedback = element("feedback");
  feedback.textContent = message.includes("\n") ? "Consulte o resultado no Diário." : message;
  feedback.classList.toggle("error", failed);
  feedback.hidden = false;
}

function showOrders(orders) {
  element("orders-panel").hidden = orders === null;
  const list = element("orders");
  list.replaceChildren();
  if (!orders) return;
  if (orders.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "Nenhuma encomenda ativa.";
    list.append(empty);
  }
  for (const order of orders) {
    const card = document.createElement("div");
    card.className = "order";
    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = label(farms[order.farm] || order.farm.replace(/-owner$/, "")) + " · " + order.id;
    const details = document.createElement("p");
    details.textContent = order.price + " moedas · qualidade " + order.quality + "+ · antes do minuto " + order.deadline;
    info.append(title, details);
    if (order.supplier) {
      const supplier = document.createElement("p");
      supplier.textContent = "Responsável: " + order.supplier;
      info.append(supplier);
    }
    card.append(info);
    if (order.open) card.append(button("Aceitar", "accept " + order.id));
    if (order.assigned_to_player) card.append(button("Entregar", "deliver " + order.id));
    list.append(card);
  }
}

function render(state) {
  element("game").hidden = false;
  element("character").textContent = state.name;
  element("location").textContent = state.destination ? "A caminho de " + label(state.destination) : label(state.location);
  element("day").textContent = "Dia " + state.day;
  element("minute").textContent = "Minuto " + state.minute;
  element("coins").textContent = state.coins;
  element("grain").textContent = state.grain;
  for (const need of ["hunger", "fatigue"]) {
    const limit = state.needs[need + "_limit"];
    element(need).max = limit;
    element(need).value = state.needs[need];
    element(need + "-label").textContent = state.needs[need] + "/" + limit;
  }
  element("exits").replaceChildren(...state.exits.map(
    (exit) => button(label(exit.location), "go " + exit.location, exit.minutes),
  ));
  if (!state.exits.length) element("exits").textContent = "Viagem em andamento.";

  const actions = [button("Esperar " + state.wait_minutes + " min", "wait " + state.wait_minutes)];
  if (!state.destination) {
    actions.unshift(button("Descansar", "rest"));
    if (state.grain > 0) actions.unshift(button("Comer grão", "eat"));
    if (state.can_try_work) actions.unshift(button(state.at_forge ? "Trabalhar na forja" : "Trabalhar no campo", "work"));
    if (state.at_forge) {
      actions.push(button("Forjar enxada", "craft hoe"));
      if (state.apprenticeship) {
        actions.push(state.knows_hammer ? button("Forjar martelo", "craft hammer") : button("Aprender a fazer martelo", "learn hammer"));
      }
    }
  }
  element("actions").replaceChildren(...actions);
  element("inventory").textContent = state.inventory;
  element("skills-panel").hidden = state.skills === null;
  element("skills").textContent = state.skills || "";
  element("market-panel").hidden = state.market === null;
  element("market").textContent = state.market || "";
  const marketActions = [button("Comprar grão", "buy")];
  if (state.career_market) marketActions.push(
    button("Comprar ferro", "buy iron"), button("Comprar lenha", "buy firewood"), button("Vender enxada", "sell hoe"),
  );
  element("market-actions").replaceChildren(...marketActions);
  showOrders(state.orders);
}

function setPending(value) {
  pending = value;
  for (const control of document.querySelectorAll("button, input")) {
    control.disabled = value || (!connected && control.id !== "reload");
  }
}

async function request(command) {
  if (pending) return;
  setPending(true);
  try {
    const response = command === undefined ? await fetch("/api/state") : await fetch("/api/command", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({command}),
    });
    const result = await response.json();
    if (!response.ok) {
      if (!connected) element("connection").textContent = "Save indisponível";
      log(result.error, true);
      return;
    }
    render(command === undefined ? result : result.state);
    connected = true;
    element("connection").textContent = "Save aberto";
    if (result.message) log(result.message);
  } catch {
    connected = false;
    element("connection").textContent = "Desconectado";
    log("Conexão interrompida. Verifique se o servidor está aberto e clique em Atualizar.", true);
  } finally {
    setPending(false);
  }
}

element("reload").addEventListener("click", () => request());
document.addEventListener("click", (event) => {
  const control = event.target.closest("button[data-command]");
  if (control) request(control.dataset.command);
});
element("command-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = element("command");
  const command = input.value.trim();
  if (pending || !command) return;
  input.value = "";
  request(command).then(() => input.focus());
});
request();
