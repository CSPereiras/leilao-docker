from flask import Flask, request, jsonify
import redis
import json
import time
import threading

app = Flask(__name__)
redis_client = redis.StrictRedis(host='redis', port=6379, decode_responses=True)

# Canal Pub/Sub para notificações
CHANNEL_AUCTION = "auction_updates"

def notify_users(message):
    """Publica uma mensagem para os usuários sobre mudanças nos leilões."""
    redis_client.publish(CHANNEL_AUCTION, json.dumps(message))

@app.route('/create_auction', methods=['POST'])
def create_auction():
    """Cria um novo leilão."""
    try:
        data = request.json

        # Obtém o próximo ID do leilão
        auction_id = redis_client.incr("auction_counter")
        auction_key = f"auction:{auction_id}"

        auction = {
            "title": data["title"],
            "description": data["description"],
            "initial_price": data["initial_price"],
            "end_time": data["end_time"],
            "active": True,
            "bids": []
        }

        redis_client.set(auction_key, json.dumps(auction))
        notify_users({"event": "auction_created", "auction_id": auction_key})
        return jsonify({
            "message": f"Leilão '{data['title']}' criado com sucesso!",
            "auction_id": auction_key,
            "title": data['title']
        })

    except Exception as e:
        print(f"Erro ao criar leilão: {e}")
        return jsonify({"error": f"Erro ao criar leilão: {e}"}), 500

@app.route('/place_bid/<auction_id>', methods=['POST'])
def place_bid(auction_id):
    """Registra um novo lance em um leilão ativo."""
    try:
        data = request.json
        username = data["username"]
        amount = data["amount"]

        auction_data = redis_client.get(auction_id)
        if not auction_data:
            return jsonify({"error": "Leilão não encontrado"}), 404

        auction = json.loads(auction_data)

        if not auction["active"]:
            return jsonify({"error": "Leilão encerrado"}), 400

        if auction["bids"] and amount <= max((bid["amount"] for bid in auction["bids"]), default=0): #linha corrigida
            return jsonify({"error": "O valor do lance deve ser maior que o atual"}), 400

        bid = {"username": username, "amount": amount, "timestamp": int(time.time())}
        auction["bids"].append(bid)
        redis_client.set(auction_id, json.dumps(auction))

        notify_users({"event": "new_bid", "auction_id": auction_id, "bid": bid})
        return jsonify({"message": "Lance registrado!", "bid": bid})

    except Exception as e:
        print(f"Erro ao registrar lance: {e}")
        return jsonify({"error": f"Erro ao registrar lance: {e}"}), 500

@app.route('/get_auction/<auction_id>', methods=['GET'])
def get_auction(auction_id):
    """Retorna os detalhes do leilão."""
    try:
        auction_data = redis_client.get(auction_id)
        if not auction_data:
            return jsonify({"error": "Leilão não encontrado"}), 404

        return jsonify(json.loads(auction_data))

    except Exception as e:
        print(f"Erro ao obter leilão: {e}")
        return jsonify({"error": f"Erro ao obter leilão: {e}"}), 500

@app.route('/close_auction/<auction_id>', methods=['POST'])
def close_auction(auction_id):
    """Fecha um leilão e define o vencedor."""
    try:
        auction_data = redis_client.get(auction_id)
        if not auction_data:
            return jsonify({"error": "Leilão não encontrado"}), 404

        auction = json.loads(auction_data)
        auction["active"] = False
        redis_client.set(auction_id, json.dumps(auction))

        notify_users({"event": "auction_closed", "auction_id": auction_id})
        return jsonify({"message": "Leilão encerrado!"})

    except Exception as e:
        print(f"Erro ao fechar leilão: {e}")
        return jsonify({"error": f"Erro ao fechar leilão: {e}"}), 500

def auction_checker():
    """Thread que monitora leilões e os fecha quando o tempo expira."""
    while True:
        try:
            keys = redis_client.keys("auction:*")
            for key in keys:
                auction_data = redis_client.get(key)
                if auction_data:
                    auction = json.loads(auction_data)
                    if auction["active"] and time.time() >= float(auction["end_time"]):
                        auction["active"] = False
                        redis_client.set(key, json.dumps(auction))
                        notify_users({"event": "auction_closed", "auction_id": key})
        except Exception as e:
            print(f"Erro na thread de verificação: {e}")
        time.sleep(5)  # Verifica a cada 5 segundos

# Iniciar a thread de verificação de leilões
#threading.Thread(target=auction_checker, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)